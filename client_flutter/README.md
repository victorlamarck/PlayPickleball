# Pickleball Live Viewer (Flutter)

A minimal spectator app for the live scores read model. It lists tournaments, shows the bracket by
round, and updates every match card the moment its Firestore document changes. There is no
login and no backend call: two snapshot listeners (`StreamBuilder` over `snapshots()`) per
screen, and nothing else.

- `lib/main.dart`: Firebase init and the emulator connection (`useFirestoreEmulator`).
- `lib/config.dart`: `--dart-define` settings and placeholder Firebase options for the emulator.
- `lib/models.dart`: pure parsing of the documents written by the backend projector.
- `lib/screens/`: tournament list and bracket. Wide screens show a column per round; phones show
  a tab per round.
- `lib/widgets/match_card.dart`: a match card that flashes and animates the numbers when a newer
  `version` changes the score.

## Run against the local emulator

With the backend running (`make up`, `make run`, `make seed` from the repository root):

```bash
cd client_flutter
flutter pub get
flutter run -d chrome                     # web: connects to localhost:8081
```

Then run `make simulate ARGS="--tournament <id> --speed 5"` in the backend and watch the cards
update.

| Target | Emulator host |
|---|---|
| Web, iOS simulator, desktop | `localhost` (default) |
| Android emulator | `10.0.2.2` (default on Android) |
| Physical device | the host's LAN IP: `--dart-define=FIRESTORE_EMULATOR_HOST=192.168.x.x` |

Other `--dart-define` options are `FIREBASE_PROJECT_ID` (default `demo-live-scores`),
`FIRESTORE_EMULATOR_PORT` (default `8081`) and `USE_FIRESTORE_EMULATOR` (default `true`).

The debug Android build allows cleartext traffic because the emulator speaks plain HTTP. Release
builds do not.

## Against a real Firebase project

Run `flutterfire configure` to generate `lib/firebase_options.dart`, then pass
`DefaultFirebaseOptions.currentPlatform` to `Firebase.initializeApp` instead of
`AppConfig.firebaseOptions`. Build with `--dart-define=USE_FIRESTORE_EMULATOR=false`. The
backend's `firestore.rules` allow public reads and deny all client writes.

## Tests

```bash
flutter analyze
flutter test   # model parsing, round names, match card rendering and the change highlight
```
