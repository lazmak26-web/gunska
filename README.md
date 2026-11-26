# Gunska Starter

A lightweight, responsive static showcase with one locally stored artwork (`public/rat.svg`). The image remains the same on every visit; the project does not call an AI image-generation API.

## Requirements
- Node.js 18 or newer
- Termux on Android, or any Linux/macOS/Windows shell with Node.js

## Run in Termux
```sh
pkg update
pkg install nodejs unzip
cd ~/storage/downloads
unzip gunska-starter.zip
cd gunska-starter
npm start
```

Open `http://localhost:3000` in your browser. To use another port:
```sh
PORT=8080 npm start
```

## Project structure
- `server.js` — small Node.js static-file server
- `index.html` — landing page
- `styles.css` — responsive styling
- `app.js` — minimal client script
- `public/rat.svg` — single static artwork

This starter is a public-facing showcase only. It contains no credential collection, hidden admin panel, ransomware, or remote-control functionality.
