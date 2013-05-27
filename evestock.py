# By Gibbous Outamon
# Program that will examine a corporation's assets, compare them to a list of
# desired assets, and report how much needs to be built/bought

import eveapi
import MySQLdb
import csv
import ConfigParser


# Total all of our owned stuff by recursing through containers
def recurseThroughContainers(rowset, totalassets):
    for item in rowset.Select("typeID", row=True):
        if len(item[0]) == 8:  # Containers have 8 fields
            recurseThroughContainers(item[0][7], totalassets)
        else:
            totalassets[item[0][1]] = totalassets.get(item[0][1], 0) + item[0][3]

config = ConfigParser.RawConfigParser()
config.read("evestock.conf")

wantlist = {}  # Dictionary of desired list of assets
totalassets = {}  # A dictionary holding our overall assets
shoppinglist = {}  # List of what we need to buy

print "Reading CSV file"
with open(config.get("evestock", "WANT_FILE"), 'rb') as csvfile:
    headerdetect = csv.Sniffer().has_header(csvfile.read(1024))
    csvfile.seek(0)
    reader = csv.reader(csvfile, delimiter=',', quotechar='"')
    if headerdetect:
        reader.next()  # Skip the header row
    for row in reader:
        wantlist[row[0]] = [row[1], row[2]]

print "Connecting to MySQL db"
db = MySQLdb.connect(
    host=config.get("evestock", "MYSQL_HOST"),
    user=config.get("evestock", "MYSQL_USER"),
    passwd=config.get("evestock", "MYSQL_PW"),
    db=config.get("evestock", "MYSQL_DB"))
cur = db.cursor()

print "Connecting to EVE API"
try:
    api = eveapi.EVEAPIConnection()
    auth = api.auth(
        keyID=config.get("evestock", "CORP_KEYID"),
        vCode=config.get("evestock", "CORP_VCODE"))
    corpassets = auth.corp.AssetList()
    assetrowset = corpassets.assets
    recurseThroughContainers(assetrowset, totalassets)
except eveapi.Error, e:
    print "Oops! eveapi returned the following error:"
    print "code:", e.code
    print "message:", e.message
    print "Obtaining inventory"

print "Inventory totaled"

print "Translating wishlist names to item IDs"
for key in wantlist.keys():
    retval = cur.execute(
        'SELECT typeID FROM invTypes WHERE typeName="%s"' % key)
    if retval != 1:
        print 'Warning: item type "%s" unrecognized. Skipping.' % key
        del wantlist[key]
    for row in cur.fetchall():
        wantlist[row[0]] = [key, int(wantlist[key][0]), int(wantlist[key][1])]
        del wantlist[key]

print "Computing purchase requirements"
for key in wantlist.keys():
    quantity = wantlist[key][1]
    # Check whether we don't have any to start with
    if key in totalassets.keys():
        quantity -= totalassets[key]
    wantlist[key][1] = quantity
    if quantity > 0:  # If we have a deficit
        # If this item is something we can build, get the material requirements
        print wantlist[key],key
	if wantlist[key][2] == 1:
	    # First, the basic materials
            cur.execute(
                "SELECT t.typeName, m.quantity FROM invTypeMaterials AS m " +
                "INNER JOIN invTypes AS t ON m.materialTypeID = t.typeID " +
                "WHERE m.typeID = %s" % key)
            for row in cur.fetchall():
                shoppinglist[row[0]] = shoppinglist.get(row[0], 0) + row[1]
            # A second query for extra materials
            cur.execute(
                "SELECT t.typeName, r.quantity, r.damagePerJob " +
                "FROM ramTypeRequirements AS r " +
                "INNER JOIN invTypes AS t " +
                "ON r.requiredTypeID = t.typeID " +
                "WHERE r.typeID = %s "
                "AND r.activityID = 1" % key)
            for row in cur.fetchall():
                shoppinglist[row[0]] = shoppinglist.get(row[0], 0) + row[1]
        #  Otherwise, add it to shopping list
        else:
            shoppinglist[wantlist[key][0]] = shoppinglist.get(key, 0) + quantity

print "Generating shopping list"
outfile = open(config.get("evestock", "OUT_FILE"), "w")
outfile.truncate()
outfile.write("Items needed for the corp hangar:\n")
for key in wantlist.keys():
    if wantlist[key][1] > 0:  # If we need some of this particular item
        outfile.write("%s: %s units\n" % (wantlist[key][0], wantlist[key][1]))
outfile.write("\nSupplies necessary to build all of these:\n")
for key in shoppinglist:
    outfile.write("%s: %s units\n" % (key, shoppinglist[key]))
