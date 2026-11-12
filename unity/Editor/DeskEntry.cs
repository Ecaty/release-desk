using System;
using System.IO;
using System.Linq;
using UnityEditor;
using UnityEditor.Build.Reporting;
using UnityEngine;

namespace ReleaseDesk.Editor
{
    /// <summary>
    /// Entry points Release Desk calls through the Unity CLI. Each returns a short text result and
    /// never reads or writes secrets.
    /// </summary>
    public static class DeskEntry
    {
        [Serializable]
        private class StoreData
        {
            public string name = "";
            public string version = "";
            public int build;
            public AndroidData android = new AndroidData();
        }

        [Serializable]
        private class AndroidData
        {
            public string package = "";
        }

        [Serializable]
        private class BuildRecord
        {
            public string result = "";
            public string version = "";
            public int build;
            public string finished = "";
            public double minutes;
            public int errors;
        }

        /// <summary>Writes name, version, build number and Android package from Store/store.json into PlayerSettings.</summary>
        public static string ApplySettings(string storeJsonPath)
        {
            var data = JsonUtility.FromJson<StoreData>(File.ReadAllText(storeJsonPath));
            if (!string.IsNullOrWhiteSpace(data.name))
                PlayerSettings.productName = data.name;
            if (!string.IsNullOrWhiteSpace(data.version))
                PlayerSettings.bundleVersion = data.version;
            if (data.build > 0)
                PlayerSettings.Android.bundleVersionCode = data.build;
            if (data.android != null && !string.IsNullOrWhiteSpace(data.android.package))
                PlayerSettings.SetApplicationIdentifier(UnityEditor.Build.NamedBuildTarget.Android, data.android.package);
            AssetDatabase.SaveAssets();
            return $"Applied: {PlayerSettings.productName} {PlayerSettings.bundleVersion} ({PlayerSettings.Android.bundleVersionCode})";
        }

        /// <summary>
        /// Builds a 64-bit Windows player into outputDirectory. The result is also written next to it as
        /// build-result.json, because a long build can outlive the CLI call that started it.
        /// </summary>
        public static string BuildWindows(string outputDirectory)
        {
            if (EditorApplication.isPlayingOrWillChangePlaymode)
                throw new InvalidOperationException("Stop Play mode before building.");
            var scenes = EditorBuildSettings.scenes.Where(s => s.enabled).Select(s => s.path).ToArray();
            if (scenes.Length == 0)
                throw new InvalidOperationException("No enabled scenes in Build Settings.");
            if (Directory.Exists(outputDirectory))
                Directory.Delete(outputDirectory, true);
            Directory.CreateDirectory(outputDirectory);
            string exe = Path.Combine(outputDirectory, SafeName(PlayerSettings.productName) + ".exe");
            var report = BuildPipeline.BuildPlayer(new BuildPlayerOptions
            {
                scenes = scenes,
                locationPathName = exe,
                target = BuildTarget.StandaloneWindows64,
                targetGroup = BuildTargetGroup.Standalone,
                options = BuildOptions.None
            });
            var summary = report.summary;
            var result = new BuildRecord
            {
                result = summary.result.ToString(),
                version = PlayerSettings.bundleVersion,
                build = PlayerSettings.Android.bundleVersionCode,
                finished = DateTime.Now.ToString("yyyy-MM-dd HH:mm"),
                minutes = Math.Round(summary.totalTime.TotalMinutes, 1),
                errors = summary.totalErrors
            };
            File.WriteAllText(Path.Combine(Path.GetDirectoryName(outputDirectory.TrimEnd('/', '\\')) ?? outputDirectory, "build-result.json"),
                JsonUtility.ToJson(result, true));
            if (summary.result != BuildResult.Succeeded)
                throw new InvalidOperationException($"Windows build {summary.result} with {summary.totalErrors} errors.");
            return $"Windows build {result.version} ({result.build}) in {result.minutes} min";
        }


        private static string SafeName(string name)
        {
            foreach (char c in Path.GetInvalidFileNameChars())
                name = name.Replace(c, '_');
            return string.IsNullOrWhiteSpace(name) ? "Game" : name;
        }
    }
}
