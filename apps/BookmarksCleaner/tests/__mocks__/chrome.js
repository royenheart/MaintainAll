/**
 * Chrome extension API mocks for unit tests.
 * Provides stubs for chrome.storage, chrome.bookmarks, chrome.runtime, etc.
 */

const storageData = { sync: {}, local: {} };

global.chrome = {
  storage: {
    sync: {
      get: (keys, callback) => {
        const defaults = typeof keys === 'object' && !Array.isArray(keys) ? keys : {};
        const result = { ...defaults };
        if (typeof keys === 'string') result[keys] = storageData.sync[keys];
        if (Array.isArray(keys)) keys.forEach(k => { result[k] = storageData.sync[k]; });
        if (typeof keys === 'object' && !Array.isArray(keys)) {
          Object.keys(keys).forEach(k => { result[k] = storageData.sync[k] ?? keys[k]; });
        }
        if (callback) callback(result);
        return Promise.resolve(result);
      },
      set: (items, callback) => {
        Object.assign(storageData.sync, items);
        if (callback) callback();
        return Promise.resolve();
      },
      getBytesInUse: () => Promise.resolve(0),
    },
    local: {
      get: (keys, callback) => {
        const defaults = typeof keys === 'object' && !Array.isArray(keys) ? keys : {};
        const result = { ...defaults };
        if (typeof keys === 'string') result[keys] = storageData.local[keys];
        if (Array.isArray(keys)) keys.forEach(k => { result[k] = storageData.local[k]; });
        if (typeof keys === 'object' && !Array.isArray(keys)) {
          Object.keys(keys).forEach(k => { result[k] = storageData.local[k] ?? keys[k]; });
        }
        if (callback) callback(result);
        return Promise.resolve(result);
      },
      set: (items, callback) => {
        Object.assign(storageData.local, items);
        if (callback) callback();
        return Promise.resolve();
      },
    },
    onChanged: { addListener: () => {} },
  },

  runtime: {
    id: 'mock-extension-id-1234567890abcdef',
    getManifest: () => ({ version: '1.1' }),
    sendMessage: () => {},
    onMessage: { addListener: () => {} },
    lastError: null,
  },

  bookmarks: {
    getTree: () => Promise.resolve([]),
    update: () => Promise.resolve(),
    create: (node) => Promise.resolve({ id: 'created-folder', title: node.title, parentId: node.parentId }),
    move: () => Promise.resolve(),
    remove: () => Promise.resolve(),
    removeTree: () => Promise.resolve(),
    search: () => Promise.resolve([]),
  },

  downloads: {
    download: () => Promise.resolve(),
  },

  permissions: {
    contains: () => Promise.resolve(true),
    request: () => Promise.resolve(true),
    remove: () => Promise.resolve(true),
  },

  alarms: {
    create: () => {},
    onAlarm: { addListener: () => {} },
  },

  notifications: {
    create: () => {},
    onButtonClicked: { addListener: () => {} },
  },

  sidePanel: {
    open: () => Promise.resolve(),
  },

  action: {
    onClicked: { addListener: () => {} },
  },

  identity: {
    getProfileUserInfo: () => Promise.resolve({ email: 'test@gmail.com', id: '1234567890' }),
  },
};

// Reset storage between tests
export function resetChromeStorage() {
  Object.keys(storageData.sync).forEach(k => delete storageData.sync[k]);
  Object.keys(storageData.local).forEach(k => delete storageData.local[k]);
}

export function setSyncStorage(key, value) {
  storageData.sync[key] = value;
}

export function setLocalStorage(key, value) {
  storageData.local[key] = value;
}
