import 'package:cloud_firestore/cloud_firestore.dart';
import 'package:firebase_core/firebase_core.dart';
import 'package:flutter/material.dart';

import 'config.dart';
import 'screens/tournament_list_screen.dart';

Future<void> main() async {
  WidgetsFlutterBinding.ensureInitialized();
  await Firebase.initializeApp(options: AppConfig.firebaseOptions);
  if (AppConfig.useEmulator) {
    FirebaseFirestore.instance.useFirestoreEmulator(
      AppConfig.emulatorHost,
      AppConfig.emulatorPort,
    );
  }
  runApp(const LiveViewerApp());
}

class LiveViewerApp extends StatelessWidget {
  const LiveViewerApp({super.key});

  @override
  Widget build(BuildContext context) {
    const seed = Color(0xFF1B7F5B); // court green
    return MaterialApp(
      title: 'Pickleball Live',
      debugShowCheckedModeBanner: false,
      theme: ThemeData(
        colorScheme: ColorScheme.fromSeed(seedColor: seed),
        useMaterial3: true,
      ),
      darkTheme: ThemeData(
        colorScheme: ColorScheme.fromSeed(
          seedColor: seed,
          brightness: Brightness.dark,
        ),
        useMaterial3: true,
      ),
      home: const TournamentListScreen(),
    );
  }
}
