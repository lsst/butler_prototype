#
# LSST Data Management System
#
# Copyright 2008-2018  AURA/LSST.
#
# This product includes software developed by the
# LSST Project (http://www.lsst.org/).
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
# You should have received a copy of the LSST License Statement and
# the GNU General Public License along with this program.  If not,
# see <https://www.lsstcorp.org/LegalNotices/>.
#

import os
import unittest

import lsst.utils.tests

from lsst.daf.butler.datastores.posixDatastore import PosixDatastore, DatastoreConfig
from datasetsHelper import FitsCatalogDatasetsHelper

try:
    import lsst.afw.table
    import lsst.afw.image
    import lsst.afw.geom
except ImportError:
    lsst.afw.table = None
    lsst.afw.image = None


class PosixDatastoreFitsTestCase(lsst.utils.tests.TestCase, FitsCatalogDatasetsHelper):

    @classmethod
    def setUpClass(cls):
        if lsst.afw.table is None:
            raise unittest.SkipTest("afw not available.")

    def setUp(self):
        self.testDir = os.path.dirname(__file__)
        self.configFile = os.path.join(self.testDir, "config/basic/butler.yaml")

    def testConstructor(self):
        datastore = PosixDatastore(config=self.configFile)
        self.assertIsNotNone(datastore)

    def testBasicPutGet(self):
        catalog = self.makeExampleCatalog()
        datastore = PosixDatastore(config=self.configFile)
        # Put
        storageClass = datastore.storageClassFactory.getStorageClass("SourceCatalog")
        uri, _ = datastore.put(catalog, storageClass=storageClass, storageHint="tester.fits", typeName=None)
        # Get
        catalogOut = datastore.get(uri, storageClass=storageClass, parameters=None)
        self.assertCatalogEqual(catalog, catalogOut)
        # These should raise
        with self.assertRaises(ValueError):
            # non-existing file
            datastore.get(uri="file:///non_existing.fits", storageClass=storageClass, parameters=None)
        with self.assertRaises(ValueError):
            # invalid storage class
            datastore.get(uri="file:///non_existing.fits", storageClass=object, parameters=None)

    def testRemove(self):
        catalog = self.makeExampleCatalog()
        datastore = PosixDatastore(config=self.configFile)
        # Put
        storageClass = datastore.storageClassFactory.getStorageClass("SourceCatalog")
        uri, _ = datastore.put(catalog, storageClass=storageClass, storageHint="tester.fits", typeName=None)
        # Get
        catalogOut = datastore.get(uri, storageClass=storageClass, parameters=None)
        self.assertCatalogEqual(catalog, catalogOut)
        # Remove
        datastore.remove(uri)
        # Get should now fail
        with self.assertRaises(ValueError):
            datastore.get(uri, storageClass=storageClass, parameters=None)
        # Can only delete once
        with self.assertRaises(FileNotFoundError):
            datastore.remove(uri)

    def testTransfer(self):
        catalog = self.makeExampleCatalog()
        path = "tester.fits"
        inputConfig = DatastoreConfig(self.configFile)
        inputConfig['datastore.root'] = os.path.join(self.testDir, "./test_input_datastore")
        inputPosixDatastore = PosixDatastore(config=inputConfig)
        outputConfig = inputConfig.copy()
        outputConfig['datastore.root'] = os.path.join(self.testDir, "./test_output_datastore")
        outputPosixDatastore = PosixDatastore(config=outputConfig)
        storageClass = outputPosixDatastore.storageClassFactory.getStorageClass("SourceCatalog")
        inputUri, _ = inputPosixDatastore.put(catalog, storageClass, path)
        outputUri, _ = outputPosixDatastore.transfer(inputPosixDatastore, inputUri, storageClass, path)
        catalogOut = outputPosixDatastore.get(outputUri, storageClass)
        self.assertCatalogEqual(catalog, catalogOut)


class PosixDatastoreExposureTestCase(lsst.utils.tests.TestCase):

    @classmethod
    def setUpClass(cls):
        if lsst.afw.image is None:
            raise unittest.SkipTest("afw not available.")

    def setUp(self):
        self.testDir = os.path.dirname(__file__)
        self.configFile = os.path.join(self.testDir, "config/basic/butler.yaml")

    def testExposurePutGet(self):
        example = os.path.join(self.testDir, "data", "basic", "small.fits")
        exposure = lsst.afw.image.ExposureF(example)
        datastore = PosixDatastore(config=self.configFile)
        # Put
        storageClass = datastore.storageClassFactory.getStorageClass("ExposureF")
        uri, comps = datastore.put(exposure, storageClass=storageClass, storageHint="test_exposure.fits",
                                   typeName=None)
        # Get
        exposureOut = datastore.get(uri, storageClass=storageClass, parameters=None)
        self.assertEqual(type(exposure), type(exposureOut))

        # Get a component
        self.assertIn("wcs", comps)
        wcs = datastore.get(comps["wcs"], storageClass=storageClass)

        # Simple check of WCS
        bbox = lsst.afw.geom.Box2I(lsst.afw.geom.Point2I(0, 0),
                                   lsst.afw.geom.Extent2I(9, 9))
        self.assertWcsAlmostEqualOverBBox(wcs, exposure.getWcs(), bbox)

    def testExposureCompositePutGet(self):
        example = os.path.join(self.testDir, "data", "basic", "small.fits")
        exposure = lsst.afw.image.ExposureF(example)
        datastore = PosixDatastore(config=self.configFile)
        # Put
        storageClass = datastore.storageClassFactory.getStorageClass("ExposureCompositeF")
        uri, comps = datastore.put(exposure, storageClass=storageClass,
                                   storageHint="test_composite_exposure.fits",
                                   typeName=None)

        # Get a component
        for c in ("wcs", ):
            self.assertIn(c, comps)
            component = datastore.get(comps[c], storageClass=storageClass.components[c])
            self.assertIsNotNone(component)

        # Simple check of WCS
        wcs = datastore.get(comps["wcs"], storageClass=storageClass.components["wcs"])
        bbox = lsst.afw.geom.Box2I(lsst.afw.geom.Point2I(0, 0),
                                   lsst.afw.geom.Extent2I(9, 9))
        self.assertWcsAlmostEqualOverBBox(wcs, exposure.getWcs(), bbox)


class MemoryTester(lsst.utils.tests.MemoryTestCase):
    pass


def setup_module(module):
    lsst.utils.tests.init()


if __name__ == "__main__":
    lsst.utils.tests.init()
    unittest.main()
