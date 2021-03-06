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

import click

from ..opt import (
    collection_type_option,
    collection_argument,
    collections_option,
    components_option,
    dataset_type_option,
    datasets_option,
    dimensions_argument,
    directory_argument,
    element_argument,
    glob_argument,
    options_file_option,
    repo_argument,
    transfer_option,
    verbose_option,
    where_option,
)

from ..utils import (
    ButlerCommand,
    split_commas,
    to_upper,
    typeStrAcceptsMultiple,
    unwrap,
)

from ... import script


willCreateRepoHelp = "REPO is the URI or path to the new repository. Will be created if it does not exist."
existingRepoHelp = "REPO is the URI or path to an existing data repository root or configuration file."
whereHelp = unwrap("""A string expression similar to a SQL WHERE clause. May involve any column of a dimension
                   table or a dimension name as a shortcut for the primary key column of a dimension
                   table.""")


# The conversion from the import command name to the butler_import function
# name for subcommand lookup is implemented in the cli/butler.py, in
# funcNameToCmdName and cmdNameToFuncName. If name changes are made here they
# must be reflected in that location. If this becomes a common pattern a better
# mechanism should be implemented.
@click.command("import", cls=ButlerCommand)
@repo_argument(required=True, help=willCreateRepoHelp)
@directory_argument(required=True)
@transfer_option()
@click.option("--export-file",
              help="Name for the file that contains database information associated with the exported "
                   "datasets.  If this is not an absolute path, does not exist in the current working "
                   "directory, and --dir is provided, it is assumed to be in that directory.  Defaults "
                   "to \"export.yaml\".",
              type=click.File("r"))
@click.option("--skip-dimensions", "-s", type=str, multiple=True, callback=split_commas,
              metavar=typeStrAcceptsMultiple,
              help="Dimensions that should be skipped during import")
@options_file_option()
def butler_import(*args, **kwargs):
    """Import data into a butler repository."""
    script.butlerImport(*args, **kwargs)


@click.command(cls=ButlerCommand)
@repo_argument(required=True, help=willCreateRepoHelp)
@click.option("--seed-config", help="Path to an existing YAML config file to apply (on top of defaults).")
@click.option("--dimension-config", help="Path to an existing YAML config file with dimension configuration.")
@click.option("--standalone", is_flag=True, help="Include all defaults in the config file in the repo, "
              "insulating the repo from changes in package defaults.")
@click.option("--override", is_flag=True, help="Allow values in the supplied config to override all "
              "repo settings.")
@click.option("--outfile", "-f", default=None, type=str, help="Name of output file to receive repository "
              "configuration. Default is to write butler.yaml into the specified repo.")
@options_file_option()
def create(*args, **kwargs):
    """Create an empty Gen3 Butler repository."""
    script.createRepo(*args, **kwargs)


@click.command(short_help="Dump butler config to stdout.", cls=ButlerCommand)
@repo_argument(required=True, help=existingRepoHelp)
@click.option("--subset", "-s", type=str,
              help="Subset of a configuration to report. This can be any key in the hierarchy such as "
              "'.datastore.root' where the leading '.' specified the delimiter for the hierarchy.")
@click.option("--searchpath", "-p", type=str, multiple=True, callback=split_commas,
              metavar=typeStrAcceptsMultiple,
              help="Additional search paths to use for configuration overrides")
@click.option("--file", "outfile", type=click.File("w"), default="-",
              help="Print the (possibly-expanded) configuration for a repository to a file, or to stdout "
              "by default.")
@options_file_option()
def config_dump(*args, **kwargs):
    """Dump either a subset or full Butler configuration to standard output."""
    script.configDump(*args, **kwargs)


@click.command(short_help="Validate the configuration files.", cls=ButlerCommand)
@repo_argument(required=True, help=existingRepoHelp)
@click.option("--quiet", "-q", is_flag=True, help="Do not report individual failures.")
@dataset_type_option(help="Specific DatasetType(s) to validate.", multiple=True)
@click.option("--ignore", "-i", type=str, multiple=True, callback=split_commas,
              metavar=typeStrAcceptsMultiple,
              help="DatasetType(s) to ignore for validation.")
@options_file_option()
def config_validate(*args, **kwargs):
    """Validate the configuration files for a Gen3 Butler repository."""
    is_good = script.configValidate(*args, **kwargs)
    if not is_good:
        raise click.exceptions.Exit(1)


@click.command(cls=ButlerCommand)
@repo_argument(required=True)
@collection_argument(help=unwrap("""COLLECTION is the Name of the collection to remove. If this is a tagged or
                          chained collection, datasets within the collection are not modified unless --unstore
                          is passed. If this is a run collection, --purge and --unstore must be passed, and
                          all datasets in it are fully removed from the data repository."""))
@click.option("--purge",
              help=unwrap("""Permit RUN collections to be removed, fully removing datasets within them.
                          Requires --unstore as an added precaution against accidental deletion. Must not be
                          passed if the collection is not a RUN."""),
              is_flag=True)
@click.option("--unstore",
              help=("""Remove all datasets in the collection from all datastores in which they appear."""),
              is_flag=True)
@options_file_option()
def prune_collection(**kwargs):
    """Remove a collection and possibly prune datasets within it."""
    script.pruneCollection(**kwargs)


@click.command(short_help="Search for collections.", cls=ButlerCommand)
@repo_argument(required=True)
@glob_argument(help="GLOB is one or more glob-style expressions that fully or partially identify the "
                    "collections to return.")
@collection_type_option()
@click.option("--chains",
              default="table",
              help=unwrap("""Affects how results are presented. TABLE lists each dataset in a row with
                          chained datasets' children listed in a Definition column. TREE lists children below
                          their parent in tree form. FLATTEN lists all datasets, including child datasets in
                          one list.Defaults to TABLE. """),
              callback=to_upper,
              type=click.Choice(("TABLE", "TREE", "FLATTEN"), case_sensitive=False))
@options_file_option()
def query_collections(*args, **kwargs):
    """Get the collections whose names match an expression."""
    table = script.queryCollections(*args, **kwargs)
    # The unit test that mocks script.queryCollections does not return a table
    # so we need the following `if`.
    if table:
        # When chains==TREE, the children of chained datasets are indented
        # relative to their parents. For this to work properly the table must
        # be left-aligned.
        table.pprint_all(align="<")


@click.command(cls=ButlerCommand)
@repo_argument(required=True)
@glob_argument(help="GLOB is one or more glob-style expressions that fully or partially identify the "
                    "dataset types to return.")
@verbose_option(help="Include dataset type name, dimensions, and storage class in output.")
@components_option()
@options_file_option()
def query_dataset_types(*args, **kwargs):
    """Get the dataset types in a repository."""
    table = script.queryDatasetTypes(*args, **kwargs)
    if table:
        table.pprint_all()
    else:
        print("No results. Try --help for more information.")


@click.command(cls=ButlerCommand)
@repo_argument(required=True)
@click.argument('dataset-type-name', nargs=1)
def remove_dataset_type(*args, **kwargs):
    """Remove a dataset type definition from a repository."""
    script.removeDatasetType(*args, **kwargs)


@click.command(cls=ButlerCommand)
@repo_argument(required=True)
@glob_argument(help="GLOB is one or more glob-style expressions that fully or partially identify the "
                    "dataset types to be queried.")
@collections_option()
@where_option(help=whereHelp)
@click.option("--find-first",
              is_flag=True,
              help=unwrap("""For each result data ID, only yield one DatasetRef of each DatasetType, from the
                          first collection in which a dataset of that dataset type appears (according to the
                          order of 'collections' passed in).  If used, 'collections' must specify at least one
                          expression and must not contain wildcards."""))
@click.option("--show-uri",
              is_flag=True,
              help="Show the dataset URI in results.")
@options_file_option()
def query_datasets(**kwargs):
    """List the datasets in a repository."""
    tables = script.queryDatasets(**kwargs)

    for table in tables:
        print("")
        table.pprint_all()
    print("")


@click.command(cls=ButlerCommand)
@repo_argument(required=True)
@click.argument('input-collection')
@click.argument('output-collection')
@click.argument('dataset-type-name')
@click.option("--begin-date", type=str, default=None,
              help=unwrap("""ISO-8601 datetime (TAI) of the beginning of the validity range for the
                          certified calibrations."""))
@click.option("--end-date", type=str, default=None,
              help=unwrap("""ISO-8601 datetime (TAI) of the end of the validity range for the
                          certified calibrations."""))
@click.option("--search-all-inputs", is_flag=True, default=False,
              help=unwrap("""Search all children of the inputCollection if it is a CHAINED collection,
                          instead of just the most recent one."""))
def certify_calibrations(*args, **kwargs):
    """Certify calibrations in a repository.
    """
    script.certifyCalibrations(*args, **kwargs)


@click.command(cls=ButlerCommand)
@repo_argument(required=True)
@dimensions_argument(help=unwrap("""DIMENSIONS are the keys of the data IDs to yield, such as exposure,
                                 instrument, or tract. Will be expanded to include any dependencies."""))
@collections_option()
@datasets_option(help=unwrap("""An expression that fully or partially identifies dataset types that should
                             constrain the yielded data IDs.  For example, including "raw" here would
                             constrain the yielded "instrument", "exposure", "detector", and
                             "physical_filter" values to only those for which at least one "raw" dataset
                             exists in "collections"."""))
@where_option(help=whereHelp)
@options_file_option()
def query_data_ids(**kwargs):
    """List the data IDs in a repository.
    """
    table = script.queryDataIds(**kwargs)
    if table:
        table.pprint_all()
    else:
        if not kwargs.get("dimensions") and not kwargs.get("datasets"):
            print("No results. Try requesting some dimensions or datasets, see --help for more information.")
        else:
            print("No results. Try --help for more information.")


@click.command(cls=ButlerCommand)
@repo_argument(required=True)
@element_argument(required=True)
@datasets_option(help=unwrap("""An expression that fully or partially identifies dataset types that should
                             constrain the yielded records. Only affects results when used with
                             --collections."""))
@collections_option(help=collections_option.help + " Only affects results when used with --datasets.")
@where_option(help=whereHelp)
@click.option("--no-check", is_flag=True,
              help=unwrap("""Don't check the query before execution. By default the query is checked before it
                          executed, this may reject some valid queries that resemble common mistakes."""))
@options_file_option()
def query_dimension_records(**kwargs):
    """Query for dimension information."""
    table = script.queryDimensionRecords(**kwargs)
    if table:
        table.pprint_all()
    else:
        print("No results. Try --help for more information.")
