# React Native Android RELRO Reproducer

Reproducer for [react-native issue #58852](https://github.com/react/react-native/issues/58852): public React Android binaries pass the 16 KB ELF LOAD alignment check but fail the GNU_RELRO end-modulo check documented by Android.

`ReproducerApp/` is unchanged from the official [react-native-community/reproducer-react-native template](https://github.com/react-native-community/reproducer-react-native/tree/181acd6681a41578c9067c0e3e3577cb033721fc). It pins React Native `0.87.1` and React `19.2.3`. This is an independent copy of that template snapshot, not a fork of React Native or a production application.

## Validation Status

- Validated: static inspection of the public `react-android:0.87.1` debug artifact, including both ARM64 and x86_64 binaries.
- Validated: checker behavior against synthetic passing, failing, missing-RELRO, 32-bit, and malformed ELF inputs.
- Not performed: dependency installation, template app build, or an Android 17 runtime reproduction.
- Automatic template cleanup, build, and updater workflows were removed. This repository does not run dependency installation or builds on push.

This demonstrates a static mismatch with the documented RELRO check, not an observed crash or proof that every flagged library is rejected by the loader. RELRO suffix layouts can be accepted by the loader even when this arithmetic check fails. Android 17's warning can also list unaffected libraries; see [Google issue 564679026](https://issuetracker.google.com/issues/564679026).

## Minimal Reproduction Without Building

Requires Python 3 and curl. The checker uses only Python's standard library and never loads or executes native libraries.

Run from the repository root:

```sh
mkdir -p artifacts
curl -fL https://repo1.maven.org/maven2/com/facebook/react/react-android/0.87.1/react-android-0.87.1-debug.aar -o artifacts/react-android-0.87.1-debug.aar
python3 -B check_relro.py artifacts/react-android-0.87.1-debug.aar
```

Expected exit code: `1`, indicating a static layout finding. Exit `0` means all inspected ARM64/x86_64 libraries passed; exit `2` means invalid input or no eligible libraries.

For every eligible ELF, the checker separately evaluates:

```text
every PT_LOAD p_align >= 0x4000
every PT_GNU_RELRO (p_vaddr + p_memsz) % 0x4000 == 0
```

Reference: [Android's 16 KB page-size guidance](https://developer.android.com/guide/practices/page-sizes), section discussing GNU_RELRO. APK ZIP alignment is a separate check and is not implemented here.

The AAR's `jni/` directory contains ten ARM64/x86_64 libraries. All ten pass LOAD alignment; nine fail the RELRO end check. Bundled FBJNI and libc++ binaries are included in that total, not attributed to React Native's own linker configuration. An AAR can also contain duplicate Prefab copies, which the checker reports separately.

React Native-owned examples:

| ABI    | Library             | VirtAddr  | MemSiz  | End       | End % 0x4000 |
| ------ | ------------------- | --------- | ------- | --------- | ------------ |
| ARM64  | libjsi.so           | 0xe4af0   | 0x5510  | 0xea000   | 0x2000       |
| x86_64 | libjsi.so           | 0xe18d0   | 0x5730  | 0xe7000   | 0x3000       |
| ARM64  | libreactnative.so   | 0x1641eb0 | 0x51150 | 0x1693000 | 0x3000       |
| x86_64 | libreactnative.so   | 0x1577c10 | 0x503f0 | 0x15c8000 | 0x0          |
| ARM64  | libhermestooling.so | 0x8a860   | 0x37a0  | 0x8e000   | 0x2000       |
| x86_64 | libhermestooling.so | 0x83210   | 0x3df0  | 0x87000   | 0x3000       |

## Template App Build Path

These instructions are provided for maintainers to build and inspect the packaged app; they have not been executed for this repository.

Use Node >= `22.11.0`, Yarn, JDK 17, and an Android SDK with the template's declared build tools `37.0.0`, compile SDK `37`, and NDK `27.1.12297006`. Configure `ANDROID_HOME` or a local, untracked `ReproducerApp/android/local.properties` as usual.

```sh
cd ReproducerApp
yarn install
cd android
./gradlew :app:assembleDebug
cd ../..
python3 -B check_relro.py ReproducerApp/android/app/build/outputs/apk/debug/app-debug.apk
```

The checker also accepts an extracted native-library directory or an individual `.so`. To inspect packaging separately, use Android SDK `zipalign -c -P 16 -v 4` on the APK. A successful ZIP alignment check does not establish RELRO compatibility.

To evaluate Android 17 behavior, install the built APK on a 16 KB page-size Android 17 device or emulator, record the actual warning and logs, and confirm device page size with `adb shell getconf PAGE_SIZE`. No such runtime evidence is claimed here.
