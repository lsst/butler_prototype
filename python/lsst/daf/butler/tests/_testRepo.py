# This file is part of daf_butler.
#
# Developed for the LSST Data Management System.
# This product includes software developed by the LSST Project
# (http://www.lsst.org).
# See the COPYRIGHT file at the top-level directory of this distribution
# for details of code ownership.
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program.  If not, see <http://www.gnu.org/licenses/>.


__all__ = ["makeTestRepo", "makeTestCollection", "addDatasetType", "expandUniqueId", "DatastoreMock",
           "addDataIdValue",
           ]

import random
from typing import (
    Any,
    Iterable,
    Mapping,
    Optional,
    Set,
    Tuple,
)
from unittest.mock import MagicMock

import sqlalchemy

from lsst.daf.butler import (
    Butler,
    Config,
    DataCoordinate,
    DatasetRef,
    DatasetType,
    Dimension,
    DimensionUniverse,
    FileDataset,
    Registry,
)


def makeTestRepo(root: str,
                 dataIds: Optional[Mapping[str, Iterable]] = None, *,
                 config: Config = None,
                 **kwargs) -> Butler:
    """Create an empty repository with dummy data IDs.

    Parameters
    ----------
    root : `str`
        The location of the root directory for the repository.
    dataIds : `~collections.abc.Mapping` [`str`, `iterable`], optional
        A mapping keyed by the dimensions used in the test. Each value
        is an iterable of names for that dimension (e.g., detector IDs for
        `"detector"`). Related dimensions (e.g., instruments and detectors)
        are linked arbitrarily. This parameter is provided for compatibility
        with old code; newer code should make the repository, then call
        `~lsst.daf.butler.tests.addDataIdValue`.
    config : `lsst.daf.butler.Config`, optional
        A configuration for the repository (for details, see
        `lsst.daf.butler.Butler.makeRepo`). If omitted, creates a repository
        with default dataset and storage types, but optimized for speed.
        The defaults set ``.datastore.cls``, ``.datastore.checksum`` and
        ``.registry.db``.  If a supplied config does not specify these values
        the internal defaults will be used to ensure that we have a usable
        configuration.
    **kwargs
        Extra arguments to `lsst.daf.butler.Butler.makeRepo`.

    Returns
    -------
    butler : `lsst.daf.butler.Butler`
        A Butler referring to the new repository. This Butler is provided only
        for additional setup; to keep test cases isolated, it is highly
        recommended that each test create its own Butler with a
        unique run/collection. See `makeTestCollection`.

    Notes
    -----
    This function provides a "quick and dirty" repository for simple unit
    tests that don't depend on complex data relationships. It is ill-suited
    for tests where the structure of the data matters. If you need such a
    dataset, create it directly or use a saved test dataset.
    """
    defaults = Config()
    defaults["datastore", "cls"] = "lsst.daf.butler.datastores.inMemoryDatastore.InMemoryDatastore"
    defaults["datastore", "checksum"] = False  # In case of future changes
    defaults["registry", "db"] = "sqlite:///<butlerRoot>/gen3.sqlite3"

    if config:
        defaults.update(config)

    if not dataIds:
        dataIds = {}

    # Disable config root by default so that our registry override will
    # not be ignored.
    # newConfig guards against location-related keywords like outfile
    newConfig = Butler.makeRepo(root, config=defaults, forceConfigRoot=False, **kwargs)
    butler = Butler(newConfig, writeable=True)
    dimensionRecords = _makeRecords(dataIds, butler.registry.dimensions)
    for dimension, records in dimensionRecords.items():
        butler.registry.insertDimensionData(dimension, *records)
    return butler


def makeTestCollection(repo: Butler) -> Butler:
    """Create a read/write Butler to a fresh collection.

    Parameters
    ----------
    repo : `lsst.daf.butler.Butler`
        A previously existing Butler to a repository, such as that returned by
        `~lsst.daf.butler.Butler.makeRepo` or `makeTestRepo`.

    Returns
    -------
    butler : `lsst.daf.butler.Butler`
        A Butler referring to a new collection in the repository at ``root``.
        The collection is (almost) guaranteed to be new.
    """
    # Create a "random" collection name
    # Speed matters more than cryptographic guarantees
    collection = "test" + str(random.randrange(1_000_000_000))
    return Butler(butler=repo, run=collection)


def _makeRecords(dataIds: Mapping[str, Iterable],
                 universe: DimensionUniverse) -> Mapping[str, Iterable]:
    """Create cross-linked dimension records from a collection of
    data ID values.

    Parameters
    ----------
    dataIds : `~collections.abc.Mapping` [`str`, `iterable`]
        A mapping keyed by the dimensions of interest. Each value is an
        iterable of names for that dimension (e.g., detector IDs for
        `"detector"`).
    universe : lsst.daf.butler.DimensionUniverse
        Set of all known dimensions and their relationships.

    Returns
    -------
    dataIds : `~collections.abc.Mapping` [`str`, `iterable`]
        A mapping keyed by the dimensions of interest, giving one
        `~lsst.daf.butler.DimensionRecord` for each input name. Related
        dimensions (e.g., instruments and detectors) are linked arbitrarily.
    """
    expandedIds = {}
    # Provide alternate keys like detector names
    for name, values in dataIds.items():
        expandedIds[name] = []
        dimension = universe[name]
        for value in values:
            expandedIds[name].append(_fillAllKeys(dimension, value))

    # Pick cross-relationships arbitrarily
    for name, values in expandedIds.items():
        dimension = universe[name]
        for value in values:
            for other in dimension.required:
                if other != dimension:
                    relation = expandedIds[other.name][0]
                    value[other.name] = relation[other.primaryKey.name]
            # Do not recurse, to keep the user from having to provide
            # irrelevant dimensions
            for other in dimension.implied:
                if other != dimension and other.name in expandedIds and other.viewOf is None:
                    relation = expandedIds[other.name][0]
                    value[other.name] = relation[other.primaryKey.name]

    return {dimension: [universe[dimension].RecordClass(**value) for value in values]
            for dimension, values in expandedIds.items()}


def _fillAllKeys(dimension: Dimension, value: Any) -> Mapping[str, Any]:
    """Create an arbitrary mapping of all required keys for a given dimension
    that do not refer to other dimensions.

    Parameters
    ----------
    dimension : `lsst.daf.butler.Dimension`
        The dimension for which to generate a set of keys (e.g., detector).
    value
        The value assigned to ``dimension`` (e.g., detector ID).

    Returns
    -------
    expandedValue : `dict` [`str`]
        A mapping of dimension keys to values. ``dimension's`` primary key
        maps to ``value``, but all other mappings (e.g., detector name)
        are arbitrary.
    """
    expandedValue = {}
    for key in dimension.uniqueKeys:
        if key.nbytes:
            castType = bytes
        else:
            castType = key.dtype().python_type
        try:
            castValue = castType(value)
        except TypeError:
            castValue = castType()
        expandedValue[key.name] = castValue
    for key in dimension.metadata:
        if not key.nullable:
            expandedValue[key.name] = key.dtype().python_type(value)
    return expandedValue


def _matchAnyDataId(record: Mapping[str, Any], registry: Registry, dimension: Dimension):
    """Matches a partial dimension record to an existing record along a
    specific dimension.

    Parameters
    ----------
    record : `dict` [`str`]
        A mapping representing the record to be matched.
    registry : `lsst.daf.butler.Registry`
        The registry with all known dimension records.
    dimension : `lsst.daf.butler.Dimension`
        The dimension on which to find a match for ``record``.

    Raises
    ------
    RuntimeError
        Raised if there are no existing records for ``dimension``.
    """
    matches = list(registry.queryDimensionRecords(dimension.name))
    if matches:
        record[dimension.name] = matches[0].dataId[dimension.name]
    else:
        raise RuntimeError(f"No matching values for {dimension.name} found.")


def _fillRelationships(dimension: Dimension,
                       dimensionInfo: Mapping[str, Any],
                       existing: Registry) -> Mapping[str, Any]:
    """Create arbitrary mappings from one dimension to all dimensions it
    depends on.

    Parameters
    ----------
    dimension : `lsst.daf.butler.Dimension`
        The dimension for which to generate relationships.
    dimensionInfo : `dict` [`str`]
        A mapping of dimension keys to values.
    existing : `lsst.daf.butler.Registry`
        The registry with all previously registered dimensions.

    Returns
    -------
    filledInfo : `dict` [`str`]
        A version of ``dimensionInfo`` with extra mappings for any
        relationships required by ``dimension``. Any relationships already
        defined in ``dimensionInfo`` are preserved.

    Raises
    ------
    ValueError
        Raised if ``dimension`` depends on a dimension for which no values
        exist yet.
    """
    filledInfo = dimensionInfo.copy()
    for other in dimension.required:
        if other != dimension and other.name not in filledInfo:
            _matchAnyDataId(filledInfo, existing, other)
    # Do not recurse, to keep the user from having to provide
    # irrelevant dimensions.
    for other in dimension.implied:
        toUpdate = other != dimension and other.name not in filledInfo
        updatable = other.viewOf is None
        # Do not run query if either toUpdate or updatable is false
        if toUpdate and updatable and list(existing.queryDimensionRecords(other)):
            _matchAnyDataId(filledInfo, existing, other)
    return filledInfo


def expandUniqueId(butler: Butler, partialId: Mapping[str, Any]) -> DataCoordinate:
    """Return a complete data ID matching some criterion.

    Parameters
    ----------
    butler : `lsst.daf.butler.Butler`
        The repository to query.
    partialId : `~collections.abc.Mapping` [`str`]
        A mapping of known dimensions and values.

    Returns
    -------
    dataId : `lsst.daf.butler.DataCoordinate`
        The unique data ID that matches ``partialId``.

    Raises
    ------
    ValueError
        Raised if ``partialId`` does not uniquely identify a data ID.

    Notes
    -----
    This method will only work correctly if all dimensions attached to the
    target dimension (eg., "physical_filter" for "visit") are known to the
    repository, even if they're not needed to identify a dataset.

    Examples
    --------
    .. code-block:: py

       >>> butler = makeTestRepo(
               "testdir", {"instrument": ["notACam"], "detector": [1]})
       >>> expandUniqueId(butler, {"detector": 1})
       DataCoordinate({instrument, detector}, ('notACam', 1))
    """
    # The example is *not* a doctest because it requires dangerous I/O
    registry = butler.registry
    dimensions = registry.dimensions.extract(partialId.keys()).required

    query = " AND ".join(f"{dimension} = {value!r}" for dimension, value in partialId.items())

    # Much of the purpose of this function is to do something we explicitly
    # reject most of the time: query for a governor dimension (e.g. instrument)
    # given something that depends on it (e.g. visit), hence check=False.
    dataId = list(registry.queryDataIds(dimensions, where=query, check=False))
    if len(dataId) == 1:
        return dataId[0]
    else:
        raise ValueError(f"Found {len(dataId)} matches for {partialId}, expected 1.")


def addDataIdValue(butler: Butler, dimension: str, value: Any, **related: str):
    """Add a new data ID to a repository.

    Related dimensions (e.g., the instrument associated with a detector) may
    be specified using ``related``. While these keywords are sometimes needed
    to get self-consistent repositories, you do not need to define
    relationships you do not use. Any unspecified dimensions will be
    linked arbitrarily.

    Parameters
    ----------
    butler : `lsst.daf.butler.Butler`
        The repository to update.
    dimension : `str`
        The name of the dimension to gain a new value.
    value
        The value to register for the dimension.
    **related
        Any existing dimensions to be linked to ``value``.

    Examples
    --------

    .. code-block::py

       addDataIdValue(butler, "skymap", "map")
       addDataIdValue(butler, "tract", 42)
       addDataIdValue(butler, "tract", 43, skymap="map")  # Redundant keyword
       for patch in [0, 1, 2, 3, 4, 5]:
           addDataIdValue(butler, "patch", patch, tract=42)
           addDataIdValue(butler, "patch", patch, tract=43)
    """
    # Example is not doctest, because it's probably unsafe to create even an
    # in-memory butler in that environment.
    try:
        fullDimension = butler.registry.dimensions[dimension]
    except KeyError as e:
        raise ValueError from e
    # Bad keys ignored by registry code
    extraKeys = related.keys() - (fullDimension.required | fullDimension.implied)
    if extraKeys:
        raise ValueError(f"Unexpected keywords {extraKeys} not found "
                         f"in {fullDimension.required | fullDimension.implied}")

    # Define secondary keys (e.g., detector name given detector id)
    expandedValue = _fillAllKeys(fullDimension, value)
    expandedValue.update(**related)
    completeValue = _fillRelationships(fullDimension, expandedValue, butler.registry)

    dimensionRecord = fullDimension.RecordClass(**completeValue)
    try:
        butler.registry.syncDimensionData(dimension, dimensionRecord)
    except sqlalchemy.exc.IntegrityError as e:
        raise RuntimeError("Could not create data ID value. Automatic relationship generation "
                           "may have failed; try adding keywords to assign a specific instrument, "
                           "filter, etc. based on the nested exception message.") from e


def addDatasetType(butler: Butler, name: str, dimensions: Set[str], storageClass: str) -> DatasetType:
    """Add a new dataset type to a repository.

    Parameters
    ----------
    butler : `lsst.daf.butler.Butler`
        The repository to update.
    name : `str`
        The name of the dataset type.
    dimensions : `set` [`str`]
        The dimensions of the new dataset type.
    storageClass : `str`
        The storage class the dataset will use.

    Returns
    -------
    datasetType : `lsst.daf.butler.DatasetType`
        The new type.

    Raises
    ------
    ValueError
        Raised if the dimensions or storage class is invalid.

    Notes
    -----
    Dataset types are shared across all collections in a repository, so this
    function does not need to be run for each collection.
    """
    try:
        datasetType = DatasetType(name, dimensions, storageClass,
                                  universe=butler.registry.dimensions)
        butler.registry.registerDatasetType(datasetType)
        return datasetType
    except KeyError as e:
        raise ValueError from e


class DatastoreMock:
    """Mocks a butler datastore.

    Has functions that mock the datastore in a butler. Provides an `apply`
    function to replace the relevent butler datastore functions with the mock
    functions.
    """

    @staticmethod
    def apply(butler):
        """Apply datastore mocks to a butler."""
        butler.datastore.export = DatastoreMock._mock_export
        butler.datastore.get = DatastoreMock._mock_get
        butler.datastore.ingest = MagicMock()

    @staticmethod
    def _mock_export(refs: Iterable[DatasetRef], *,
                     directory: Optional[str] = None,
                     transfer: Optional[str] = None) -> Iterable[FileDataset]:
        """A mock of `Datastore.export` that satisfies the requirement that
        the refs passed in are included in the `FileDataset` objects
        returned.

        This can be used to construct a `Datastore` mock that can be used
        in repository export via::

            datastore = unittest.mock.Mock(spec=Datastore)
            datastore.export = DatastoreMock._mock_export

        """
        for ref in refs:
            yield FileDataset(refs=[ref],
                              path="mock/path",
                              formatter="lsst.daf.butler.formatters.json.JsonFormatter")

    @staticmethod
    def _mock_get(ref: DatasetRef, parameters: Optional[Mapping[str, Any]] = None
                  ) -> Tuple[int, Optional[Mapping[str, Any]]]:
        """A mock of `Datastore.get` that just returns the integer dataset ID
        value and parameters it was given.
        """
        return (ref.id, parameters)
