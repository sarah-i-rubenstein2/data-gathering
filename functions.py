from shapely.geometry import Polygon, shape
import math
import numpy as np
import random
import cv2

# returns an array of classified roi objects and polygon points
def getRois(conn, image):
    output = []
    roi_service = conn.getRoiService()
    rois = roi_service.findByImage(image.getId(), None).rois
    for i in range(0, len(rois)):
        shape = rois[i].getShape(0)
        roi = {
            "id": rois[i].getId().getValue()
        }
        if(str(type(shape)) == "<class 'omero.model.PolygonI'>"):
            points = shape.getPoints().getValue()
            color = shape.getStrokeColor()._val
            gleason = "None"
            if(color == 822031103):
                gleason = "Grade 3"
            elif(color == -387841):
                gleason = "Grade 4 FG"
            elif(color == -32047105):
                gleason = "Grade 4 CG"
            elif(color == 570425343):
                gleason = "Grade 5"

            roi["points"] = points
            roi["gleason"] = gleason

            # only want to process tumor annotations
            if(roi["gleason"] != "None"):
                output.append(roi)

    return output

# create a shapely polygon from the string returned by Omero
def polygonFromPoints(pointsStr):
    # split into ordered pairs
    pairsStr = pointsStr.split()

    # loop through each ordered pair and split into arrays of points 
    pairs = []
    for i in range(0, len(pairsStr)):
        pair = pairsStr[i].split(',')
        pairs.append(pair)

    # create polygon
    return Polygon(pairs)

# get tile bounds of mxn diimensions from a polygon
def tileBoundsFromPolygon(polygon, m, n):
    # get a bounding box around the polygon
    boundary = polygon.bounds # (minx, miny, maxx, maxy)
    minx = boundary[0]
    miny = boundary[1]
    maxx = boundary[2]
    maxy = boundary[3]

    box = Polygon([[minx, miny], [maxx, miny], [maxx, maxy], [minx, maxy]])
    
    numXTiles = math.floor((maxx-minx)/m)
    numYTiles = math.floor((maxy-miny)/n)

    tiles = []

    # split box into 500x500 tiles (roughly)
    xPoint = minx
    yPoint = miny
    for i in range(0, numXTiles+1):
        for j in range(0, numYTiles+1):
            tiles.append(Polygon([[xPoint, yPoint], [xPoint+m, yPoint], [xPoint+m, yPoint+n], [xPoint, yPoint+n]]))
            yPoint = yPoint + n
        
        xPoint = xPoint + m
        yPoint = miny

    # remove tiles that are not >50% overlapped
    i = 0
    while(i < len(tiles)):
        box2 = tiles[i]
        percentOverlap = 0
        if(polygon.intersects(box2)):
            # check for self-intersection
            if(polygon.is_valid):
                percentOverlap = polygon.intersection(box2).area / box2.area
            else:
                try:
                    fixedPolygon = polygon.buffer(0)
                    percentOverlap = fixedPolygon.intersection(box2).area / box2.area
                except:
                    print("intersection could not be fixed, discarding")
                    percentOverlap = 0

        if(percentOverlap < 0.5):
            tiles.remove(box2)
            # want to be on correct index after removal
            i = i - 1 
        i = i + 1

    return tiles

# get tiles given bounding boxes
def findTiles(pixels, boxes):
    input = []
    for i in range(0, len(boxes)):
        box = boxes[i]
        # get smallest x and y values to originate from
        minx = math.floor(box.bounds[0])
        miny = math.floor(box.bounds[1])
        width = math.floor(box.bounds[2] - minx)
        height = math.floor(box.bounds[3] - miny)

        # get all three channels
        input.append((0, 0, 0, (minx, miny, width, height)))
        input.append((0, 1, 0, (minx, miny, width, height)))
        input.append((0, 2, 0, (minx, miny, width, height)))

    tiles = pixels.getTiles(input)

    output = []
    # combine channels
    i = 0
    rg = []
    for tile in tiles:
        if(i == 2):
            rgb = np.dstack((rg[0], rg[1], tile))
            output.append(rgb)
            i = 0
            rg = []
        else:
            rg.append(tile)
            i = i+1

    return output

# get all roi tiles from an image
def getTilesFromImage(imgId, conn):
    image = conn.getObject("Image", imgId)
    roiObjs = getRois(conn, image)

    finalTiles = []

    allPolygons = []

    for roi in roiObjs:
        # get polygon's points
        currRoi = roi["points"]
        
        # get the bounds of each tile
        poly = polygonFromPoints(currRoi)
        tileList = tileBoundsFromPolygon(poly, 500, 500)
        allPolygons.append(poly)

        # get image tiles
        pixels = image.getPrimaryPixels()
        tiles = findTiles(pixels, tileList)

        for tile in tiles:
            if(isBackground(tile) == False):
                finalTiles.append({
                    "tile": tile,
                    "roiId": roi["id"],
                    "imgId": image.getId(),
                    "gleason": roi["gleason"]
                })

    # image tiles, polygons
    return finalTiles, allPolygons

# get mxn boxes along the edge of an image
def getEdgeBoxes(sizex, sizey, m, n):
    boxes = []

    #skip some images because we don't need so many
    skipFactor = 60

    # top edge
    for i in range(0, sizex-500, m*skipFactor):
        box = Polygon([[i, 0], [i+500, 0], [i+500, 500], [i, 500]])
        boxes.append(box)
    # bottom edge
    for i in range(0, sizex-500, m*skipFactor):
        box = Polygon([[i, sizey-500], [i+500, sizey-500], [i+500, sizey], [i, sizey]])
        boxes.append(box)
    # left edge
    for i in range(0, sizey-500, n*skipFactor):
        box = Polygon([[0, i], [500, i], [500, i+500], [0, i+500]])
        boxes.append(box)
    # right edge
    for i in range(0, sizey-500, n*skipFactor):
        box = Polygon([[sizex-500, i], [sizex, i], [sizex, i+500], [sizex-500, i+500]])
        boxes.append(box)

    return boxes

def getEdgeTilesFromImage(imgId, conn, m, n):
    image = conn.getObject("Image", imgId)
    sizex = image.getSizeX()
    sizey = image.getSizeY()

    finalTiles = []

    # get edge boxes
    boxes = getEdgeBoxes(sizex, sizey, m, n)

    # get image tiles
    pixels = image.getPrimaryPixels()
    tiles = findTiles(pixels, boxes)

    for tile in tiles:
        if(isBackground(tile) == True):
            finalTiles.append({
                "tile": tile,
                "roiId": "none",
                "imgId": image.getId(),
                "gleason": "background"
            })

    return finalTiles, boxes

def getUnlabeledTilesFromImage(imgId, conn, m, n, allBoxes):
    image = conn.getObject("Image", imgId)
    sizex = image.getSizeX()
    sizey = image.getSizeY()

    finalTiles = []

    # find 800 (random) unlabeled boxes
    validBoxes = 0
    boxes = []
    while(validBoxes < 800):
        randX = random.random()*(sizex - 1000)
        randY = random.random()*(sizey - 1000)
        box = Polygon([[randX, randY], [randX+500, randY], [randX+500, randY+500], [randX, randY+500]])
        
        intersects = False
        for polygon in allBoxes:
            if(box.intersects(polygon)):
                intersects = True
                break
        
        if(intersects == False):
            validBoxes += 1
            boxes.append(box)

    # get image tiles
    pixels = image.getPrimaryPixels()
    tiles = findTiles(pixels, boxes)

    for tile in tiles:
        if(isBackground(tile) == False):
            finalTiles.append({
                "tile": tile,
                "roiId": "none",
                "imgId": image.getId(),
                "gleason": "unlabeled"
            })

    return finalTiles

def isBackground(tile):
    hsv = cv2.cvtColor(tile, cv2.COLOR_RGB2HSV)

    lower = np.array([0,10,0])
    upper = np.array([255,255,255])

    mask = cv2.inRange(hsv, lower, upper)
    res = cv2.bitwise_and(tile, tile, mask = mask)

    # is background if less than 75000 non-white pixels
    if (np.count_nonzero(res) < 75000):
        return True

    return False