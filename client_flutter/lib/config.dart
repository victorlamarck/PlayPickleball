import 'package:firebase_core/firebase_core.dart';
import 'package:flutter/foundation.dart';

/// Runtime configuration through `--dart-define`. The defaults target the local
/// Firestore emulator from the backend's docker-compose (project `demo-live-scores`).
///
/// Examples:
///   `flutter run -d chrome`
///   `flutter run -d <android-device> --dart-define=FIRESTORE_EMULATOR_HOST=192.168.0.10`
class AppConfig {
  static const projectId = String.fromEnvironment(
    'FIREBASE_PROJECT_ID',
    defaultValue: 'demo-live-scores',
  );
  static const useEmulator = bool.fromEnvironment(
    'USE_FIRESTORE_EMULATOR',
    defaultValue: true,
  );
  static const emulatorPort = int.fromEnvironment(
    'FIRESTORE_EMULATOR_PORT',
    defaultValue: 8081,
  );
  static const _emulatorHostOverride = String.fromEnvironment(
    'FIRESTORE_EMULATOR_HOST',
  );

  /// The Android emulator reaches the host machine at 10.0.2.2; web and iOS
  /// simulators use localhost. A physical device needs the host's LAN IP.
  static String get emulatorHost {
    if (_emulatorHostOverride.isNotEmpty) return _emulatorHostOverride;
    if (!kIsWeb && defaultTargetPlatform == TargetPlatform.android) {
      return '10.0.2.2';
    }
    return 'localhost';
  }

  /// Placeholder options: enough for the emulator, which ignores credentials.
  /// For a real Firebase project, generate `firebase_options.dart` with
  /// `flutterfire configure` and use those options instead.
  static FirebaseOptions get firebaseOptions => FirebaseOptions(
    apiKey: 'demo-api-key',
    appId: _appId,
    messagingSenderId: '000000000000',
    projectId: projectId,
    iosBundleId: 'dev.livescores.pickleballLiveViewer',
  );

  static String get _appId {
    if (kIsWeb) return '1:000000000000:web:0000000000000000';
    return switch (defaultTargetPlatform) {
      TargetPlatform.iOS => '1:000000000000:ios:0000000000000000',
      _ => '1:000000000000:android:0000000000000000',
    };
  }
}
