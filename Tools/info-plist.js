// macOS Foundation preserves plist types without an extra runtime dependency.
ObjC.import('Foundation');

function read(path) {
    var value = $.NSDictionary.dictionaryWithContentsOfFile($(path));
    if (ObjC.unwrap(value) === undefined) throw new Error('Cannot read plist dictionary: ' + path);
    return value;
}
function has(dict, key) { return dict.allKeys.containsObject(key); }
function equal(a, b) { return a.isEqual(b); }
function inputMetadata(key) {
    // On the first build there is no baseline for user edits. Refresh packaging
    // metadata, but preserve project settings such as permissions and URL schemes.
    return /^(DT|BuildMachineOSBuild$)/.test(key) || [
        'CFBundleExecutable', 'CFBundleIdentifier', 'CFBundleName',
        'CFBundleVersion', 'CFBundleShortVersionString',
        'CFBundleInfoDictionaryVersion', 'CFBundlePackageType',
        'CFBundleSupportedPlatforms', 'CFBundleSignature',
        'CFBundleIcons', 'CFBundleIcons~ipad', 'CFBundleIconFiles', 'CFBundleIconName',
        'MinimumOSVersion', 'LSRequiresIPhoneOS', 'UIDeviceFamily',
        'UIMainStoryboardFile', 'UIMainStoryboardFile~ipad',
        'UILaunchStoryboardName', 'UILaunchStoryboardName~ipad',
        'UISupportedDevices', 'UIRequiredDeviceCapabilities'
    ].indexOf(key) !== -1;
}
function write(dict, path) {
    if (!dict.writeToFileAtomically($(path), true)) throw new Error('Cannot write plist: ' + path);
}
function run(args) {
    if (args[0] === 'commit') {
        var pending = read(args[1]).mutableCopy;
        pending.setObjectForKey(read(args[2]), $('generated'));
        write(pending, args[3]);
        return;
    }
    var input = read(args[1]), current = read(args[2]);
    var state = $.NSFileManager.defaultManager.fileExistsAtPath($(args[3])) ? read(args[3]) : null;
    var values = state ? state.objectForKey($('values')).mutableCopy : $.NSMutableDictionary.dictionary;
    var deleted = state ? state.objectForKey($('deleted')).mutableCopy : $.NSMutableArray.array;
    var previous = state ? state.objectForKey($('generated')) : null;
    var previousInput = state ? state.objectForKey($('input')) : input;
    // Missing keys on the first build are not evidence of a user deletion.
    if (!state) previous = input;
    if (previous) {
        var keys = $.NSMutableSet.setWithArray(state ? previous.allKeys : current.allKeys);
        keys.addObjectsFromArray(current.allKeys);
        var all = keys.allObjects;
        for (var i = 0; i < all.count; i++) {
            var key = all.objectAtIndex(i), present = has(current, key);
            if (!state && inputMetadata(ObjC.unwrap(key))) continue;
            if (present && has(previous, key) && equal(current.objectForKey(key), previous.objectForKey(key))) continue;
            if (!present) {
                values.removeObjectForKey(key);
                if (!deleted.containsObject(key)) deleted.addObject(key);
            } else {
                deleted.removeObject(key);
                if (has(previousInput, key) && equal(current.objectForKey(key), previousInput.objectForKey(key))) values.removeObjectForKey(key);
                else values.setObjectForKey(current.objectForKey(key), key);
            }
        }
    }
    var output = input.mutableCopy;
    output.addEntriesFromDictionary(values);
    for (var j = 0; j < deleted.count; j++) output.removeObjectForKey(deleted.objectAtIndex(j));
    output.setObjectForKey(input.objectForKey($('CFBundleExecutable')), $('CFBundleExecutable'));
    write(output, args[4]);
    var next = $.NSMutableDictionary.dictionary;
    next.setObjectForKey(values, $('values'));
    next.setObjectForKey(deleted, $('deleted'));
    next.setObjectForKey(input, $('input'));
    write(next, args[5]);
}
