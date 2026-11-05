// Run the normal Node-RED CLI, with a graceful file-based stop for our launcher.
const fs = require('fs');
const path = require('path');
const [red, profile, stop] = process.argv.slice(2);
if (!red || !profile || !stop) process.exit(2);
process.argv = [process.execPath, path.resolve(red), '--userDir', path.resolve(profile)];
require(path.resolve(red));
let stopping = false;
process.once('SIGINT', () => { stopping = true; });
const timer = setInterval(() => {
  if (!stopping && fs.existsSync(stop)) { stopping = true; process.emit('SIGINT'); }
}, 250);
timer.unref();
