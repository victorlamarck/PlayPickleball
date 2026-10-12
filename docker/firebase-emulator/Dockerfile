# Firestore emulator + Emulator Suite UI (Firebase CLI). Local development and CI only.
FROM node:24-trixie-slim

RUN apt-get update \
    && apt-get install -y --no-install-recommends openjdk-21-jre-headless curl \
    && rm -rf /var/lib/apt/lists/*

RUN npm install -g firebase-tools@15.33.0 \
    && firebase setup:emulators:firestore \
    && firebase setup:emulators:ui

# firebase.json and firestore.rules are mounted by docker-compose (edits apply on restart).
WORKDIR /firebase

ENV FIREBASE_CLI_DISABLE_UPDATE_CHECK=true
EXPOSE 4000 4400 8081 9150
CMD ["firebase", "emulators:start", "--only", "firestore", "--project", "demo-live-scores"]
