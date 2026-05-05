import { app } from 'electron';
console.log(app ? app.getVersion() : "app is undefined");
