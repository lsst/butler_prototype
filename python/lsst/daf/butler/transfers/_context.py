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

from __future__ import annotations

__all__ = ["RepoExportContext"]

from typing import (
    Callable,
    Dict,
    Iterable,
    List,
    Optional,
    Set,
    Union,
)
from collections import defaultdict

from ..core import (
    DataCoordinate,
    DatasetAssociation,
    DimensionElement,
    DimensionRecord,
    DatasetRef,
    DatasetType,
    Datastore,
    FileDataset,
)
from ..registry import CollectionType, Registry
from ..registry.interfaces import ChainedCollectionRecord, CollectionRecord
from ._interfaces import RepoExportBackend


class RepoExportContext:
    """Public interface for exporting a subset of a data repository.

    Instances of this class are obtained by calling `Butler.export` as the
    value returned by that context manager::

        with butler.export(filename="export.yaml") as export:
            export.saveDataIds(...)
            export.saveDatasets(...)

    Parameters
    ----------
    registry : `Registry`
        Registry to export from.
    datastore : `Datastore`
        Datastore to export from.
    backend : `RepoExportBackend`
        Implementation class for a particular export file format.
    directory : `str`, optional
        Directory to pass to `Datastore.export`.
    transfer : `str`, optional
        Transfer mdoe to pass to `Datastore.export`.
    """

    def __init__(self, registry: Registry, datastore: Datastore, backend: RepoExportBackend, *,
                 directory: Optional[str] = None, transfer: Optional[str] = None):
        self._registry = registry
        self._datastore = datastore
        self._backend = backend
        self._directory = directory
        self._transfer = transfer
        self._records: Dict[DimensionElement, Dict[DataCoordinate, DimensionRecord]] = defaultdict(dict)
        self._dataset_ids: Set[int] = set()
        self._datasets: Dict[DatasetType, Dict[str, List[FileDataset]]] \
            = defaultdict(lambda: defaultdict(list))
        self._collections: Dict[str, CollectionRecord] = {}

    def saveCollection(self, name: str) -> None:
        """Export the given collection.

        Parameters
        ----------
        name: `str`
            Name of the collection.

        Notes
        -----
        `~CollectionType.RUN` collections are also exported automatically when
        any dataset referencing them is exported.  They may also be explicitly
        exported this method to export the collection with no datasets.
        Duplicate exports of collections are ignored.

        Exporting a `~CollectionType.TAGGED` or `~CollectionType.CALIBRATION`
        collection will cause its associations with exported datasets to also
        be exported, but it does not export those datasets automatically.

        Exporting a `~CollectionType.CHAINED` collection does not automatically
        export its child collections; these must be explicitly exported or
        already be present in the repository they are being imported into.
        """
        self._collections[name] = self._registry._collections.find(name)

    def saveDimensionData(self, element: Union[str, DimensionElement],
                          records: Iterable[Union[dict, DimensionRecord]]) -> None:
        """Export the given dimension records associated with one or more data
        IDs.

        Parameters
        ----------
        element : `str` or `DimensionElement`
            `DimensionElement` or `str` indicating the logical table these
            records are from.
        records : `Iterable` [ `DimensionRecord` or `dict` ]
            Records to export, as an iterable containing `DimensionRecord` or
            `dict` instances.
        """
        if not isinstance(element, DimensionElement):
            element = self._registry.dimensions[element]
        for record in records:
            if not isinstance(record, DimensionRecord):
                record = element.RecordClass(**record)
            elif record.definition != element:
                raise ValueError(
                    f"Mismatch between element={element.name} and "
                    f"dimension record with definition={record.definition.name}."
                )
            self._records[element].setdefault(record.dataId, record)

    def saveDataIds(self, dataIds: Iterable[DataCoordinate], *,
                    elements: Optional[Iterable[Union[str, DimensionElement]]] = None) -> None:
        """Export the dimension records associated with one or more data IDs.

        Parameters
        ----------
        dataIds : iterable of `DataCoordinate`.
            Data IDs to export.  For large numbers of data IDs obtained by
            calls to `Registry.queryDataIds`, it will be much more efficient if
            these are expanded to include records (i.e.
            `DataCoordinate.hasRecords` returns `True`) prior to the call to
            `saveDataIds` via e.g. ``Registry.queryDataIds(...).expanded()``.
        elements : iterable of `DimensionElement` or `str`, optional
            Dimension elements whose records should be exported.  If `None`,
            records for all dimensions will be exported.
        """
        if elements is None:
            elements = frozenset(element for element in self._registry.dimensions.getStaticElements()
                                 if element.hasTable() and element.viewOf is None)
        else:
            elements = set()
            for element in elements:
                if not isinstance(element, DimensionElement):
                    element = self._registry.dimensions[element]
                if element.hasTable() and element.viewOf is None:
                    elements.add(element)
        for dataId in dataIds:
            # This is potentially quite slow, because it's approximately
            # len(dataId.graph.elements) queries per data ID.  But it's a no-op
            # if the data ID is already expanded, and DM-26692 will add (or at
            # least start to add / unblock) query functionality that should
            # let us speed this up internally as well.
            dataId = self._registry.expandDataId(dataId)
            for record in dataId.records.values():
                if record is not None and record.definition in elements:
                    self._records[record.definition].setdefault(record.dataId, record)

    def saveDatasets(self, refs: Iterable[DatasetRef], *,
                     elements: Optional[Iterable[Union[str, DimensionElement]]] = None,
                     rewrite: Optional[Callable[[FileDataset], FileDataset]] = None) -> None:
        """Export one or more datasets.

        This automatically exports any `DatasetType`, `~CollectionType.RUN`
        collections, and dimension records associated with the datasets.

        Parameters
        ----------
        refs : iterable of `DatasetRef`
            References to the datasets to export.  Their `DatasetRef.id`
            attributes must not be `None`.  Duplicates are automatically
            ignored.  Nested data IDs must have `DataCoordinate.hasRecords`
            return `True`.
        elements : iterable of `DimensionElement` or `str`, optional
            Dimension elements whose records should be exported; this is
            forwarded to `saveDataIds` when exporting the data IDs of the
            given datasets.
        rewrite : callable, optional
            A callable that takes a single `FileDataset` argument and returns
            a modified `FileDataset`.  This is typically used to rewrite the
            path generated by the datastore.  If `None`, the `FileDataset`
            returned by `Datastore.export` will be used directly.

        Notes
        -----
        At present, this only associates datasets with `~CollectionType.RUN`
        collections.  Other collections will be included in the export in the
        future (once `Registry` provides a way to look up that information).
        """
        dataIds = set()
        for ref in sorted(refs):
            # The query interfaces that are often used to generate the refs
            # passed here often don't remove duplicates, so do that here for
            # convenience.
            if ref.id in self._dataset_ids:
                continue
            dataIds.add(ref.dataId)
            # `exports` is a single-element list here, because we anticipate
            # a future where more than just Datastore.export has a vectorized
            # API and we can pull this out of the loop.
            exports = self._datastore.export([ref], directory=self._directory, transfer=self._transfer)
            if rewrite is not None:
                exports = [rewrite(export) for export in exports]
            self._dataset_ids.add(ref.getCheckedId())
            assert ref.run is not None
            self._datasets[ref.datasetType][ref.run].extend(exports)
        self.saveDataIds(dataIds, elements=elements)

    def _finish(self) -> None:
        """Delegate to the backend to finish the export process.

        For use by `Butler.export` only.
        """
        for element in self._registry.dimensions.sorted(self._records.keys()):
            # To make export deterministic sort the DataCoordinate instances.
            r = self._records[element]
            self._backend.saveDimensionData(element, *[r[dataId] for dataId in sorted(r.keys())])
        for datasetsByRun in self._datasets.values():
            for run in datasetsByRun.keys():
                self._collections[run] = self._registry._collections.find(run)
        for collectionName in self._computeSortedCollections():
            doc = self._registry.getCollectionDocumentation(collectionName)
            self._backend.saveCollection(self._collections[collectionName], doc)
        # Sort the dataset types and runs before exporting to ensure
        # reproducible order in export file.
        for datasetType in sorted(self._datasets.keys()):
            for run in sorted(self._datasets[datasetType].keys()):
                # Sort the FileDataset
                records = sorted(self._datasets[datasetType][run])
                self._backend.saveDatasets(datasetType, run, *records)
        # Export associations between datasets and collections.  These need to
        # be sorted (at two levels; they're dicts) or created more
        # deterministically, too, which probably involves more data ID sorting.
        datasetAssociations = self._computeDatasetAssociations()
        for collection in sorted(datasetAssociations):
            self._backend.saveDatasetAssociations(collection, self._collections[collection].type,
                                                  sorted(datasetAssociations[collection]))
        self._backend.finish()

    def _computeSortedCollections(self) -> List[str]:
        """Sort collections in a way that is both deterministic and safe
        for registering them in a new repo in the presence of nested chains.

        This method is intended for internal use by `RepoExportContext` only.

        Returns
        -------
        names: `List` [ `str` ]
            Ordered list of collection names.
        """
        # Split collections into CHAINED and everything else, and just
        # sort "everything else" lexicographically since there are no
        # dependencies.
        chains: Dict[str, List[str]] = {}
        result: List[str] = []
        for record in self._collections.values():
            if record.type is CollectionType.CHAINED:
                assert isinstance(record, ChainedCollectionRecord)
                chains[record.name] = list(record.children)
            else:
                result.append(record.name)
        result.sort()
        # Sort all chains topologically, breaking ties lexicographically.
        # Append these to 'result' and remove them from 'chains' as we go.
        while chains:
            unblocked = {
                parent for parent, children in chains.items()
                if not any(child in chains.keys() for child in children)
            }
            if not unblocked:
                raise RuntimeError("Apparent cycle in CHAINED collection "
                                   f"dependencies involving {unblocked}.")
            result.extend(sorted(unblocked))
            for name in unblocked:
                del chains[name]
        return result

    def _computeDatasetAssociations(self) -> Dict[str, List[DatasetAssociation]]:
        """Return datasets-collection associations, grouped by association.

        This queries for all associations between exported datasets and
        exported TAGGED or CALIBRATION collections and is intended to be run
        only by `_finish`, as this ensures all collections and all datasets
        have already been exported and hence the order in which they are
        exported does not matter.

        Returns
        -------
        associations : `dict` [ `str`, `list` [ `DatasetAssociation` ] ]
            Dictionary keyed by collection name, with values lists of structs
            representing an association between that collection and a dataset.
        """
        results = defaultdict(list)
        for datasetType in self._datasets.keys():
            # We query for _all_ datasets of each dataset type we export, in
            # the specific collections we are exporting.  The worst-case
            # efficiency of this is _awful_ (i.e. big repo, exporting a tiny
            # subset).  But we don't have any better options right now; we need
            # a way to query for a _lot_ of explicitly given dataset_ids, and
            # the only way to make that scale up is to either upload them to a
            # temporary table or recognize when they are already in one because
            # the user passed us a QueryResult object.  That's blocked by (at
            # least) DM-26692.
            collectionTypes = {CollectionType.TAGGED}
            if datasetType.isCalibration():
                collectionTypes.add(CollectionType.CALIBRATION)
            associationIter = self._registry.queryDatasetAssociations(
                datasetType,
                collections=self._collections.keys(),
                collectionTypes=collectionTypes,
                flattenChains=False,
            )
            for association in associationIter:
                if association.ref.id in self._dataset_ids:
                    results[association.collection].append(association)
        return results
