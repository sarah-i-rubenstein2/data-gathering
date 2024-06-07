# data-gathering

*Note:* Your "default group" in Omero must be set to the group you're tring to get images from, or it won't be able to get the ROIs

This code is directly from this repo, so it is tailored to my uses

## Basic steps to using Omero python toolbox:

### 0. Set up Omero python toolbox 

https://omero-guides.readthedocs.io/en/latest/python/docs/setup.html

### 1. Establish a connection
```
from omero.gateway import BlitzGateway, MapAnnotationWrapper
conn = BlitzGateway("USERNAME", "PASSWORD", host="wss://wsi.lavlab.mcw.edu/omero-wss", port=443, secure=True)
conn.connect()
conn.c.enableKeepAlive(60)
```

### 2. Get ROIs
```
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
```

### 3. Create a Shapely polygon from the "points" string in an ROI
```
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
```

### 4. Get 500x500 bounding boxes (shapely polygons) from around an ROI
*Note:* 500x500 tiles suited my purposes best, but are not always necessary
```
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

    return tiles
```

### 5. Get tiles given bounding boxes
```
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
```
