import 'package:flutter/material.dart';
import 'package:flutter/services.dart';

import 'home.dart';
import 'l10n/app_localizations.dart';
import 'notifications.dart';

Future<void> main() async {
  WidgetsFlutterBinding.ensureInitialized();
  await RunNotifications.initialize();
  SystemChrome.setEnabledSystemUIMode(SystemUiMode.edgeToEdge);
  SystemChrome.setSystemUIOverlayStyle(
    SystemUiOverlayStyle.dark.copyWith(
      statusBarColor: Colors.transparent,
      systemNavigationBarColor: Colors.transparent,
    ),
  );
  runApp(const OpenImagineApp());
}

class OpenImagineApp extends StatelessWidget {
  const OpenImagineApp({super.key});

  @override
  Widget build(BuildContext context) {
    const cream = Color(0xFFF6F4F1);
    const ink = Color(0xFF111111);
    const ink2 = Color(0xFF4D4D4D);
    const line = Color(0xFFC7C1B8);
    return MaterialApp(
      onGenerateTitle: (context) => AppLocalizations.of(context).appTitle,
      localizationsDelegates: AppLocalizations.localizationsDelegates,
      supportedLocales: AppLocalizations.supportedLocales,
      title: 'Open Imagine',
      theme: ThemeData(
        useMaterial3: true,
        splashFactory: NoSplash.splashFactory,
        splashColor: Colors.transparent,
        highlightColor: Colors.transparent,
        hoverColor: Colors.transparent,
        scaffoldBackgroundColor: cream,
        colorScheme:
            ColorScheme.fromSeed(
              seedColor: ink,
              brightness: Brightness.light,
            ).copyWith(
              primary: ink,
              onPrimary: Colors.white,
              surface: cream,
              onSurface: ink,
            ),
        textTheme: const TextTheme(
          headlineMedium: TextStyle(
            fontFamily: 'serif',
            fontSize: 34,
            height: 1.1,
            color: ink,
          ),
          bodyLarge: TextStyle(fontSize: 15, height: 1.5, color: ink),
          bodySmall: TextStyle(fontSize: 12, height: 1.5, color: ink2),
        ),
        filledButtonTheme: FilledButtonThemeData(
          style: FilledButton.styleFrom(
            backgroundColor: ink,
            foregroundColor: Colors.white,
            overlayColor: Colors.transparent,
            minimumSize: const Size.fromHeight(48),
            shape: RoundedRectangleBorder(
              borderRadius: BorderRadius.circular(10),
            ),
            textStyle: const TextStyle(
              fontSize: 15,
              fontWeight: FontWeight.w500,
            ),
          ),
        ),
        outlinedButtonTheme: OutlinedButtonThemeData(
          style: OutlinedButton.styleFrom(
            foregroundColor: ink,
            overlayColor: Colors.transparent,
            side: const BorderSide(color: line),
            minimumSize: const Size.fromHeight(48),
            shape: RoundedRectangleBorder(
              borderRadius: BorderRadius.circular(10),
            ),
          ),
        ),
        textButtonTheme: TextButtonThemeData(
          style: TextButton.styleFrom(
            foregroundColor: ink2,
            overlayColor: Colors.transparent,
          ),
        ),
      ),
      home: const HomePage(),
    );
  }
}
