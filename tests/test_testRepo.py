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

"""Unit tests for `lsst.daf.butler.tests.testRepo`, a module for creating
test repositories or butlers.
"""

import os
import shutil
import tempfile
import unittest

from lsst.daf.butler.tests import makeTestButler, addDatasetType


TESTDIR = os.path.abspath(os.path.dirname(__file__))


class ButlerUtilsTestSuite(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        # Butler or collection should be re-created for each test case, but
        # this has a prohibitive run-time cost at present
        cls.root = tempfile.mkdtemp(dir=TESTDIR)

        dataIds = {}
        dataIds["instrument"] = [{"name": "notACam"}]
        dataIds["physical_filter"] = [{
            "name": "k2020",
            "instrument": "notACam",
        }]
        dataIds["visit"] = [{
            "id": 101,
            "name": "unique_visit",
            "instrument": "notACam",
            "physical_filter": "k2020",
        }]
        dataIds["detector"] = [{
            "id": 5,
            "full_name": "chip_5",
            "instrument": "notACam",
        }]
        cls.butler = makeTestButler(cls.root, dataIds)

        addDatasetType(cls.butler, "DataType1", {"instrument"}, "NumpyArray")
        addDatasetType(cls.butler, "DataType2", {"instrument", "visit", "detector"}, "NumpyArray")

    @classmethod
    def tearDownClass(cls):
        # TODO: use addClassCleanup rather than tearDownClass in Python 3.8
        # to keep the addition and removal together and make it more robust
        shutil.rmtree(cls.root, ignore_errors=True)

    def testButlerValid(self):
        self.butler.validateConfiguration()

    def _checkButlerDimension(self, dimensions, query, expected):
        result = [id for id in self.butler.registry.queryDimensions(
            dimensions,
            where=query,
            expand=False)]
        self.assertEqual(len(result), 1)
        self.assertEqual(dict(result[0]), expected)

    def testButlerDimensions(self):
        self. _checkButlerDimension({"instrument"},
                                    "instrument='notACam'",
                                    {"instrument": "notACam"})
        self. _checkButlerDimension({"visit", "instrument"},
                                    "visit.name='unique_visit'",
                                    {"instrument": "notACam", "visit": 101})
        self. _checkButlerDimension({"detector", "instrument"},
                                    "detector.full_name='chip_5'",
                                    {"instrument": "notACam", "detector": 5})

    def testAddDatasetType(self):
        self.assertEqual(len(self.butler.registry.getAllDatasetTypes()), 2)

        # Testing the DatasetType objects is not practical, because all tests
        # need a DimensionUniverse. So just check that we have the dataset
        # types we expect.
        self.butler.registry.getDatasetType("DataType1")
        self.butler.registry.getDatasetType("DataType2")

        with self.assertRaises(ValueError):
            addDatasetType(self.butler, "DataType3", {"4thDimension"}, "NumpyArray")
        with self.assertRaises(ValueError):
            addDatasetType(self.butler, "DataType3", {"instrument"}, "UnstorableType")


if __name__ == "__main__":
    unittest.main()
