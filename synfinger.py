#!/usr/bin/env python

import numpy as np
import matplotlib.pyplot as plt
import matplotlib.cm as cm
import matplotlib.lines as lines
from PIL import Image
import scipy as sp
import scipy.signal as spsig
import scipy.io as sio
import scipy.ndimage.filters as filt
import math
import random
from mpl_toolkits.mplot3d import axes3d
from ImgUtils import scaleImg, binarize
import uuid
import cv2
import os


img = cv2.imread('1.jpg', 1)
path = '/Users/graciecarter/Documents/GitHub/Salutation/python-fingerprint-recognition/database'
cv2.imwrite(os.path.join(path,'fin1' ), img)
cv2.waitKey(0)

# import scipy.stsci.convolve as convolve


class SynFinger:
    """
  Generates a synthetic finger master image according to the SFINGE method. 
  Additional parameters added to simulate rolled prints.
  Returns dictionary:
      image: nd-array as list
      size: (row,col) tuple
      core: nd-array as list
      singularpoints: {ls: nd-array as list, ds: nd-array as list}
      henry: string
      orientationmap: nd-array as list
  """

    def __init__(self, remoteDebug=False):

        if remoteDebug:
            try:
                import wingdbstub
            except ImportError:
                assert False, 'Could not load remote dubugger module. Aborting.'

        # Returnable values for DB
        self.size = None
        self.core = []
        self.singularpoints = []
        self.henry = ''
        self.image = []
        self.orientationmap = []

    def make_master(self, size=(640, 640), henry=None, plotResult=False, fname=None, returnValue=True):

        self.size = size
        self.henry = henry

        # Generate image size then create singular points for Henry type
        mask = np.ones(self.size, dtype=np.int)
        ls, ds = self.makeSingularPts(mask, self.henry)

        if self.henry != 'Whorl':  # see makeSingularPts return comment for why you have to do this here
            ls = [ls]
            ds = [ds]
        ls = np.array(ls)
        ds = np.array(ds)

        self.singularpoints = {'ls': ls.tolist(), 'ds': ds.tolist()}
        # print ls, ds
        # print self.singularpoints

        # Determine core point as midpoint between two loop singularities or the position of the loop
        if ls.ndim > 1:
            self.core = np.average(ls, axis=0)
        else:
            self.core = ls

        # Generate orientation map
        orientMap = self.makeOrientationMap(ls, ds, mask, self.henry)
        self.orientationmap = np.array(orientMap)

        # Gabor filter to generate grayscale image, then binarize for master image
        masterImage = self.gaborFilter(orientMap)
        masterImage = binarize(masterImage)
        self.image = np.array(masterImage)

        if fname:
            self.makeImage(masterImage, filename=fname)

        if plotResult:
            plt.figure()
            plt.imshow(masterImage, cmap=cm.gray)

            for ls1 in ls:
                plt.plot(ls1[1], ls1[0], 'o')
            for ds1 in ds:
                plt.plot(ds1[1], ds1[0], '^')
            plt.plot(self.core[1], self.core[0], 'r*')

            # numRows, numCols = np.shape(orientMap)
            # for r in range(0,numRows,3):
            # for c in range(0,numCols,3):
            # plt.plot([c,c+2.0*math.cos(orientMap[r][c])],[r,r+2.0*math.sin(orientMap[r][c])],'g-')
            plt.show()

        if returnValue:
            return_dict = {'image': self.image.tolist(), 'size': self.size, 'core': self.core.tolist(),
                           'singularpoints': self.singularpoints, 'orientationmap': self.orientationmap.tolist(),
                           'henry': self.henry}
            return return_dict

    def genMask(self, a1, a2, b1, b2, c, d=0):
        """
    Generates a finger foreground mask with a center rectangle dxc (WxH) and
    major axes (b1,b2) (top,bottom), minor axes (a1,a2) (right,left)
    """

        # Force even numbers for a well-defined center point
        if c % 2 == 1: c = c + 1
        if d & d % 2 == 1: d = d + 1

        # Calculate limits of the mask and create zero array
        numRows = c + b1 + b2
        numCols = d + a1 + a2
        mask = np.zeros((numRows, numCols), dtype='int8')

        # Loop through each row starting at top of image
        # Calculate left and right limits and set mask to 1 inbetween
        for r in range(0, numRows):
            if r >= b1 + c:
                # Ellipses defined by b2 major axis, a2/a1 minor (notation reversed)
                centerR = b1 + c;
                centerC = a2 + (d / 2);
                leftLim = centerC - float(a2) * math.sqrt(1.0 - (float(r - centerR) / float(b2)) ** 2) - (d / 2)
                rightLim = centerC + float(a1) * math.sqrt(1.0 - (float(r - centerR) / float(b2)) ** 2) + 1 + (d / 2)
            elif r > b1:
                # In the middle rectangle, no ellipses required
                leftLim = 0
                righLim = numCols
            else:
                # Ellipses defined by b1 major, a2/a1 minor axes (notation reversed)
                centerR = b1;
                centerC = a2 + (d / 2);
                leftLim = centerC - float(a2) * math.sqrt(1.0 - (float(centerR - r) / float(b1)) ** 2) - (d / 2)
                rightLim = centerC + float(a1) * math.sqrt(1.0 - (float(centerR - r) / float(b1)) ** 2) + 1 + (d / 2)

            # Check for out of bounds due to float math, truncate to int
            if leftLim < 0:
                leftLim = 0
            else:
                leftLim = int(leftLim)
            if rightLim > numCols:
                rightLim = numCols
            else:
                rightLim = int(rightLim)

            # Set mask to 1 in areas where fingerprint will be generated
            mask[r, leftLim:rightLim] = 1

        return mask

    def makeSingularPts(self, mask, henry=None):
        """
        Creates loop and delta points based on the Henry class (randomized placement)
        """
        numRows, numCols = np.shape(mask)
        if not henry:
            henry = random.choice(('Left Loop', 'Right Loop', 'Whorl', 'Tented Arch'))
            self.henry = henry

        if henry == 'Arch':
            # Put a loop below mask area FIXME: This doesn't work (maybe some kind of gaussian?)
            # ls=[random.randint(numRows,2*numRows),random.randint(.2*numCols,.8*numCols)]
            ls = [random.randint(int(.4 * numRows), int(.6 * numRows)),
                  random.randint(int(.4 * numCols), int(.6 * numCols))]
            # ds=[ls[0]+numRows, ls[1]]
            ds = ls
            # ls=[ls]
            # ds=[ds]

        elif henry == 'Left Loop':
            # Put one loop in top half of fingeprint, center +/- 10% 
            ls = [random.randint(int(.4 * numRows), int(.6 * numRows)),
                  random.randint(int(.4 * numCols), int(.6 * numCols))]
            # Find maximum distance to edge of fingerprint, put 1 delta at random
            # angle in correct quadrant
            dsOffDist = random.uniform(.2, .7) * math.sqrt((numRows - ls[0]) ** 2 + (numCols - ls[1]) ** 2)
            dsOffAngle = random.uniform(math.pi / 8.0, 3.0 * math.pi / 8.0)
            ds = [ls[0] + int(dsOffDist * math.sin(dsOffAngle)), ls[1] + int(dsOffDist * math.cos(dsOffAngle))]
            # ls=[ls]
            # ds=[ds]

        elif henry == 'Right Loop':
            # Put one loop in top half of fingeprint, center +/- 20% 
            ls = [random.randint(int(.4 * numRows), int(.6 * numRows)),
                  random.randint(int(.4 * numCols), int(.6 * numCols))]
            # Find  offset distance (20-70% to edge of fingerprint), put 1 delta at random
            # angle in correct quadrant
            dsOffDist = random.uniform(.2, .7) * math.sqrt((numRows - ls[0]) ** 2 + (ls[1]) ** 2)
            dsOffAngle = random.uniform(math.pi / 8.0, 3.0 * math.pi / 8.0) + math.pi / 2.0
            ds = [ls[0] + int(dsOffDist * math.sin(dsOffAngle)), ls[1] + int(dsOffDist * math.cos(dsOffAngle))]
            # ls=[ls]
            # ds=[ds]

        elif henry == 'Tented Arch':
            ls = [random.randint(int(.4 * numRows), int(.6 * numRows)),
                  random.randint(int(.4 * numCols), int(.6 * numCols))]
            ds = [ls[0] + random.randint(10, numRows - ls[0]) - 1, ls[1]]
            # ls=[ls]
            # ds=[ds]

        elif henry == 'Whorl':
            ls1, ds1 = self.makeSingularPts(mask, henry='Right Loop')
            ls2, ds2 = self.makeSingularPts(mask, henry='Left Loop')
            print(ls1, ls2, ds1, ds2)
            ls = [ls1, ls2]
            ds = [ds1, ds2]

        else:
            assert false, 'Invalid Fingerprint Type'

        # this return is complicated, if it's anything but Whorl, need to wrap it up in extra list braces on return
        # All need to be converted to np.array outside this function because of recursion in the Whorl function
        return (ls, ds)

    def makeOrientationMap(self, ls, ds, mask, henry=None):
        """
        Generates an orientation map based on the Henry class of fingerprint
        """

        numRows, numCols = np.shape(mask)
        orientMap = np.zeros((numRows, numCols), dtype='float')

        # Calculate the Sherlock-Munro Model with Vizcaya-Gerhardt Correction
        # Signs reversed due to way rows are indexed in Python

        if ds.ndim > 1:
            for r in range(0, numRows):
                for c in range(0, numCols):
                    Z_ds = np.sum([self.gAlpha(math.atan2((r - ds[i][0]), (c - ds[i][1]))) for i in range(0, len(ds))])
                    Z_ls = np.sum([self.gAlpha(math.atan2((r - ls[i][0]), (c - ls[i][1]))) for i in range(0, len(ls))])
                    orientMap[r, c] = 0.5 * (Z_ls - Z_ds)
        else:
            for r in range(0, numRows):
                for c in range(0, numCols):
                    Z_ds = np.sum([self.gAlpha(math.atan2((r - ds[0]), (c - ds[1])))])
                    Z_ls = np.sum([self.gAlpha(math.atan2((r - ls[0]), (c - ls[1])))])
                    orientMap[r, c] = 0.5 * (Z_ls - Z_ds)

        return orientMap

    def gAlpha(self, a):
        """
    Helper function for the Vizcaya-Gerhardt correction to the orientation map
    """
        if a > math.pi: a = a - 2.0 * math.pi

        a_axis = np.linspace(-math.pi, math.pi, num=9, endpoint=True)
        gA = np.linspace(-math.pi, math.pi, num=9, endpoint=True)
        # henry = 'Right Loop'
        # if henry == 'Right Loop':
        # gA[4] -= math.pi/3.0
        # gA[3] -= math.pi*2.0/9.0
        # gA[5] -= math.pi*2.0/9.0
        # if henry == 'Left Loop':
        # gA[4] += math.pi/3.0
        # gA[3] += math.pi*2.0/9.0
        # gA[5] += math.pi*2.0/9.0

        g_ai = max(gA[a_axis <= a])
        try:
            g_aip1 = min(gA[a_axis > a])
        except Exception:
            return max(gA)
        g_diff = g_aip1 - g_ai
        a_diff = a - max(a_axis[a_axis <= a])
        gk_alpha = g_ai + a_diff / (2.0 * math.pi / 8) * g_diff

        # print a, gk_alpha
        return gk_alpha

    def gaborFilter(self, orientMap: object) -> object:
        """
        Applies Gabor filters to generate a ridge structure based on local orientation
        """
        numRows, numCols = np.shape(orientMap)
        masterImage = np.zeros((numRows, numCols), dtype='float')

        # Create a spatially varying frequency response
        # Uses a tukey window to lower freq above/below singular pts
        nr = np.linspace(0, 1, numRows)
        tukey = np.ones(nr.shape, dtype='float')
        alpha = 0.7
        first = nr < alpha / 2.0
        tukey[first] = 0.5 * (1 + np.cos(2 * np.pi / alpha * (nr[first] - alpha / 2.0)))
        third = nr >= 1 - alpha / 2.0
        tukey[third] = 0.5 * (1 + np.cos(2 * np.pi / alpha * (nr[third] - 1 + alpha / 2.0)))
        tukey = 3.0 * (1.0 - tukey)
        spatialFreq = 7.5 * np.ones((numRows, numCols), dtype='float')
        for r in range(0, numRows):
            spatialFreq[r] = spatialFreq[r] + tukey[r]

        for n in range(1, 4000):
            # print n
            # Seed with N initial points, keeping them inside filter overlap boundary 
            # so no edge effects during inital seeding
            filtSize: int = 16
            N = 8
            outBound = filtSize / 2 + 1
            seedPointsR = np.random.randint(outBound, numRows - outBound, N)
            seedPointsC = np.random.randint(outBound, numCols - outBound, N)

            # During first two iterations, put a dirac to stimulate filter
            # response 
            if n < 2:
                for i in range(0, N):
                    masterImage[seedPointsR[i], seedPointsC[i]] = 1.0

            # Do Monte Carlo sampling of N points, applying Gabor filter at
            # at each point
            for i in range(0, N):
                th = orientMap[seedPointsR[i], seedPointsC[i]] - math.pi / 2.0

                r = seedPointsR[i]
                c: None = seedPointsC[i]

                f = 1.0 / spatialFreq[r, c]
                sig = -1.0 * (3.0 / (2.0 * f)) ** 2 / math.log(10.0 ** (-3)) / 2.0

                filtCoef = [[math.exp(-1.0 * (float(x) ** 2 + float(y) ** 2) / (2.0 * sig)) * math.cos(
                    2.0 * math.pi * f * (float(x) * math.cos(th) + float(y) * math.sin(th))) for x in
                             range(-filtSize // 2, filtSize // 2)] for y in range(-filtSize // 2, filtSize // 2)]

                filtCoef = np.array(filtCoef)

                fs2 = filtSize / 2
                appArea = masterImage[int(r - fs2):int(r + fs2), int(c - fs2):int(c + fs2)].copy()
                testVar = spsig.fftconvolve(appArea, filtCoef, mode='same')

                # Test for malformed response and replace
                if np.isnan(testVar).any():
                    testVar[np.where(np.isnan(testVar))] = 0.0
                if np.isinf(testVar).any():
                    testVar[np.where(np.isinf(testVar))] = 0.0

                # Scale each time to adjust contrast    
                if (np.max(testVar) - np.min(testVar)) > 0:
                    testVar *= (255.0 / (np.max(testVar) - np.min(testVar)))
                    testVar += abs(np.min(testVar))

                masterImage[int(r - fs2):int(r + fs2), int(c - fs2):int(c + fs2)] = testVar

        # After all seeding complete, do entire image with 50% window overlap
        for r in range(int(fs2), int(numRows - fs2), int(fs2)):
            for c in range(int(fs2), int(numCols - fs2), int(fs2)):
                th = orientMap[r, c] - math.pi / 2.0

                f = 1.0 / spatialFreq[r, c]
                sig = -1.0 * (3.0 / (2.0 * f)) ** 2 / math.log(10.0 ** (-3)) / 2.0

                filtCoef = []
                for y in range(-filtSize // 2, filtSize // 2):
                    filtCoef.append([math.exp(-1.0 * (float(x) ** 2 + float(y) ** 2) / (2.0 * sig)) * math.cos(
                        2.0 * math.pi * f * (float(x) * math.cos(th) + float(y) * math.sin(th))) for x in
                                     range(-filtSize // 2, filtSize // 2)])

                filtCoef = np.array(filtCoef)

                fs2 = filtSize / 2
                appArea = masterImage[int(r - fs2):int(r + fs2), int(c - fs2):int(c + fs2)].copy()
                testVar = spsig.fftconvolve(appArea, filtCoef, mode='same')

                if np.isnan(testVar).any():
                    testVar[np.where(np.isnan(testVar))] = 0.0
                if np.isinf(testVar).any():
                    testVar[np.where(np.isinf(testVar))] = 0.0

                if (np.max(testVar) - np.min(testVar)) > 0:
                    testVar *= (255.0 / (np.max(testVar) - np.min(testVar)))
                    testVar += abs(np.min(testVar))

                masterImage[int(r - fs2):int(r + fs2), int(c - fs2):int(c + fs2)] = testVar

        # Moving average filter to get rid of windowing effects            
        masterImage = spsig.fftconvolve(masterImage, np.ones((4, 4), dtype='int'), mode='same')
        masterImage = scaleImg(masterImage)
        return masterImage

    def applyMask(self, thresImage, mask):
        """
        Applies the finger shape mask to the ridge structure and returns print
        """
        maskImage = np.multiply(mask, threshImage)
        maskImage[np.where(mask == 0)] = 255
        return maskImage

    def makeImage(self, maskImage, filename=None):
        """
        Takes image as NP array and converts to TIF format
        """
        if not filename:
            filename = uuid.uuid4()

        numRows, numCols = np.shape(maskImage)
        im = Image.new("L", (numCols, numRows), 255)
        for r in range(0, numRows):
            for c in range(0, numCols):
                im.im.putpixel((c, r), maskImage[r, c])
        im.save(filename)


if __name__ == '__main__':
    synf = SynFinger();
    retval = synf.make_master(size=(640, 640), henry='Tented Arch', plotResult=True, returnValue=True)
