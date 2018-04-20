/* Cycript - The Truly Universal Scripting Language
 * Copyright (C) 2009-2016  Jay Freeman (saurik)
*/

/* GNU Affero General Public License, Version 3 {{{ */
/*
 * This program is free software: you can redistribute it and/or modify
 * it under the terms of the GNU Affero General Public License as published by
 * the Free Software Foundation, either version 3 of the License, or
 * (at your option) any later version.

 * This program is distributed in the hope that it will be useful,
 * but WITHOUT ANY WARRANTY; without even the implied warranty of
 * MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
 * GNU Affero General Public License for more details.

 * You should have received a copy of the GNU Affero General Public License
 * along with this program.  If not, see <http://www.gnu.org/licenses/>.
**/
/* }}} */

(function() {

Number.prototype.__defineGetter__('$cyt', function() {
    if (this.$cyt_)
        return this.$cyt_;
    if ((this|0) == this)
        return int;
});

this.typeid = function(object) {
    return object.$cyt;
};

let $cy_set = function(object, properties) {
    for (const name in properties)
        if ("defineProperty" in Object)
        Object.defineProperty(object, name, {
            configurable: true,
            enumerable: false,
            writable: true,
            value: properties[name],
        }); else object[name] = properties[name];
};

$cy_set(Boolean.prototype, {
    toCYON: function() {
        return `new Boolean(${this.toString()})`;
    },
});

$cy_set(Date.prototype, {
    toCYON: function() {
        return `new ${this.constructor.name}(${this.toUTCString().toCYON()})`;
    },
});

$cy_set(Error.prototype, {
    toCYON: function() {
        let stack = this.stack;
        if (typeof stack == 'undefined')
            stack = '';
        else {
            stack = stack.split('\n');
            if (stack.slice(-1)[0] == "global code")
                stack = stack.slice(0, -1);
            for (let i = 0; i != stack.length; ++i)
                stack[i] = '\n    ' + stack[i];
            if (stack.length == 0)
                stack = '';
            else {
                stack = stack.join('');
                stack = ` /*${stack} */`;
            }
        }
        return `new ${this.constructor.name}(${this.message.toCYON()})${stack}`;
    },
});

$cy_set(Number.prototype, {
    toCYON: function() {
        if ("$cyt" in this)
            //return `${this.$cyt.toCYON()}(${this.toString()})`;
            return this.toString();
        return `new Number(${this.toString()})`;
    },
});

$cy_set(RegExp.prototype, {
    toCYON: function() {
        return this.toString();
    },
});

if ("ObjectiveC" in Cycript) {
    $cy_set(NSArray.prototype, {
        $cyg: function(key) {
            return objc_msgSend(this, "objectAtIndex:", key);
        },

        $cys: function(key, value) {
            return objc_msgSend(this, "setObject:atIndex:", value, key);
        },
    });

    $cy_set(NSDictionary.prototype, {
        $cyg: function(key) {
            return objc_msgSend(this, "objectForKey:", key);
        },

        $cys: function(key, value) {
            return objc_msgSend(this, "setObject:forKey:", value, key);
        },
    });
}

let IsFile = function(path) {
    // XXX: this doesn't work on symlinks, but I don't want to fix stat :/
    return access(path, F_OK) == 0 && access(path + '/', F_OK) == -1;
};

let StartsWith = function(lhs, rhs) {
    return lhs.substring(0, rhs.length) == rhs;
};

let ResolveFile = function(exact, name) {
    if (exact && IsFile(name))
        return name;
    for (let suffix of ['.js', '.json'])
        if (IsFile(name + suffix))
            return name + suffix;
    return null;
};

let GetDocumentPath = function() {
    return NSSearchPathForDirectoriesInDomains(NSDocumentDirectory,1,true)[0];
};

let GetLibraryPath = function() {
    let handle = dlopen(NULL, RTLD_NOLOAD);
    if (handle == null)
        return null;

    try {
        let CYListenServer = dlsym(handle, "CYListenServer");
        if (CYListenServer == null)
            return null;

        let info = new Dl_info;
        if (dladdr(CYListenServer, info) == 0)
            return null;

        let path = info->dli_fname;
        let slash = path.lastIndexOf('/');
        if (slash == -1)
            return null;

        path = path.substr(0, slash);

        GetLibraryPath = function() {
            return path;
        };

        return GetLibraryPath();
    } finally {
        dlclose(handle);
    }
};

let ResolveFolder = function(name) {
    if (access(name + '/', F_OK) == -1)
        return null;

    if (IsFile(name + "/package.json")) {
        let package = require(name + "/package.json");
        let path = ResolveFile(true, name + "/" + package.main);
        if (path != null)
            return path;
    }

    return ResolveFile(false, name + "/index");
};

let ResolveEither = function(name) {
    let path = null;
    if (path == null)
        path = ResolveFile(true, name);
    if (path == null)
        path = ResolveFolder(name);
    return path;
};

require.resolve = function(name) {
    if (StartsWith(name, '/')) {
        let path = ResolveEither(name);
        if (path != null)
            return path;
    } else {
        let cwd = *new (typedef char[1024]);
        cwd = getcwd(cwd, cwd.length).toString();
        cwd = cwd.split('/');

        if (StartsWith(name, './') || StartsWith(name, '../')) {
            let path = ResolveEither(cwd + '/' + name);
            if (path != null)
                return path;
        } else {

            for (let i = cwd.length; i != 0; --i) {
                let modules = cwd.slice(0, i).concat("node_modules").join('/');
                let path = ResolveEither(modules + "/" + name);
                if (path != null)
                    return path;
            }

            let library = GetLibraryPath();
            let path = ResolveFile(true, library + "/" + name + ".cy");
            if (path != null)
                return path;

            let document = GetDocumentPath();
            path = ResolveFile(true, document + "/cycript/" + name + ".cy");
            if (path != null)
                return path;
        }
    }

    throw new Error("Cannot find module '" + name + "'");
};

var _syscall = function(value) {
    if (value == -1)
        throw new Error(strerror(errno));
};

var info = *new (struct stat);
if (false) {
} else if ("st_atim" in info) {
    var st_atime = "st_atim";
    var st_mtime = "st_mtim";
    var st_ctime = "st_ctim";
} else if ("st_atimespec" in info) {
    var st_atime = "st_atimespec";
    var st_mtime = "st_mtimespec";
    var st_ctime = "st_ctimespec";
} else {
    var st_atime = "st_atime";
    var st_mtime = "st_mtime";
    var st_ctime = "st_ctime";
}

var toDate = function(timespec) {
    return new Date(timespec.tv_sec * 1000 + timespec.tv_nsec / 1000);
};

var bindings = {};

process.binding = function(name) {
    let binding = bindings[name];
    if (typeof binding != 'undefined')
        return binding;

    switch (name) {
        case 'buffer': binding = {
            setupBufferJS() {
            },
        }; break;

        case 'cares_wrap': binding = {
        }; break;

        case 'constants': binding = {
        }; break;

        case 'fs': binding = {
            FSInitialize() {
            },

            lstat(path) {
                var info = new (struct stat);
                _syscall(lstat(path, info));

                return {
                    dev: info->st_dev,
                    mode: info->st_mode,
                    nlink: info->st_nlink,
                    uid: info->st_uid,
                    gid: info->st_gid,
                    rdev: info->st_rdev,
                    blksize: info->st_blksize,
                    ino: info->st_ino,
                    size: info->st_size,
                    blocks: info->st_blocks,

                    atime: toDate(info->[st_atime]),
                    mtime: toDate(info->[st_mtime]),
                    ctime: toDate(info->[st_ctime]),

                    isSymbolicLink() {
                        return S_ISLNK(this.mode);
                    },
                };
            },
        }; break;

        case 'pipe_wrap': binding = {
        }; break;

        case 'smalloc': binding = {
            alloc() {
            },
        }; break;

        case 'stream_wrap': binding = {
        }; break;

        case 'tcp_wrap': binding = {
        }; break;

        case 'timer_wrap': binding = {
            kOnTimeout: 0,
            Timer: {
            },
        }; break;

        case 'tty_wrap': binding = {
        }; break;

        case 'uv': binding = {
        }; break;

        default:
            throw new Error('No such module: ' + name);
    }

    bindings[name] = binding;
    return binding;
};

process.env = {};

let environ = *(typedef char ***)(dlsym(RTLD_DEFAULT, "environ"));
for (let i = 0; environ[i] != null; ++i) {
    let assign = environ[i];
    let equal = assign.indexOf('=');
    let name = assign.substr(0, equal);
    let value = assign.substr(equal + 1);
    process.env[name.toString()] = value;
}

process.cwd = function() {
    let cwd = new (typedef char[1024]);
    return getcwd(cwd, cwd.length).toString();
};

process.pid = getpid();

})();
