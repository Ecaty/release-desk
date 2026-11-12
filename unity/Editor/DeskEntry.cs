using System;
using System.IO;
using System.Linq;
using UnityEditor;
using UnityEditor.Build;
using UnityEditor.Build.Reporting;
using UnityEngine;

namespace ReleaseDesk.Editor
{
    /// <summary>
    /// Entry points Release Desk calls through the Unity CLI. They never read or write secrets.
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
            public string target = "";
            public string path = "";
            public string version = "";
            public int build;
            public bool development;
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
                PlayerSettings.SetApplicationIdentifier(NamedBuildTarget.Android, data.android.package);
            AssetDatabase.SaveAssets();
            return $"Applied: {PlayerSettings.productName} {PlayerSettings.bundleVersion} ({PlayerSettings.Android.bundleVersionCode})";
        }

        /// <summary>
        /// Builds a player. target: "windows" or "android". For Windows, path is the folder; for Android, the .apk/.aab file
        /// (.aab builds an App Bundle). The result is written to resultPath as JSON, because a long build can outlive
        /// the CLI call that started it. The previous active platform is restored afterwards. For an Android release,
        /// keystore and credential name the upload keystore and its Windows Credential Manager entry (alias "upload").
        /// </summary>
        public static string Build(string target, string path, bool development, string resultPath, string keystore = "", string credential = "")
        {
            if (EditorApplication.isPlayingOrWillChangePlaymode)
                throw new InvalidOperationException("Stop Play mode before building.");
            var scenes = EditorBuildSettings.scenes.Where(s => s.enabled).Select(s => s.path).ToArray();
            if (scenes.Length == 0)
                throw new InvalidOperationException("No enabled scenes in Build Settings.");
            var previousTarget = EditorUserBuildSettings.activeBuildTarget;
            var previousGroup = BuildPipeline.GetBuildTargetGroup(previousTarget);
            bool bundle = path.EndsWith(".aab", StringComparison.OrdinalIgnoreCase);
            var options = new BuildPlayerOptions { scenes = scenes, options = development ? BuildOptions.Development : BuildOptions.None };
            switch (target)
            {
                case "windows":
                    if (Directory.Exists(path))
                        Directory.Delete(path, true);
                    Directory.CreateDirectory(path);
                    options.locationPathName = Path.Combine(path, SafeName(PlayerSettings.productName) + ".exe");
                    options.target = BuildTarget.StandaloneWindows64;
                    options.targetGroup = BuildTargetGroup.Standalone;
                    break;
                case "android":
                    Directory.CreateDirectory(Path.GetDirectoryName(path) ?? ".");
                    EditorUserBuildSettings.buildAppBundle = bundle;
                    options.locationPathName = path;
                    options.target = BuildTarget.Android;
                    options.targetGroup = BuildTargetGroup.Android;
                    break;
                default:
                    throw new ArgumentException("Unknown target " + target);
            }
            var started = DateTime.Now;
            BuildReport report;
            var key = target == "android" && !string.IsNullOrEmpty(keystore) ? new UploadKey(keystore, credential, "upload") : null;
            try
            {
                report = BuildPipeline.BuildPlayer(options);
            }
            finally
            {
                key?.Dispose();
                if (EditorUserBuildSettings.activeBuildTarget != previousTarget)
                    EditorUserBuildSettings.SwitchActiveBuildTarget(previousGroup, previousTarget);
            }
            var summary = report.summary;
            var record = new BuildRecord
            {
                result = summary.result.ToString(),
                target = target,
                path = path,
                version = PlayerSettings.bundleVersion,
                build = PlayerSettings.Android.bundleVersionCode,
                development = development,
                finished = DateTime.Now.ToString("yyyy-MM-dd HH:mm"),
                minutes = Math.Round((DateTime.Now - started).TotalMinutes, 1),
                errors = summary.totalErrors
            };
            Directory.CreateDirectory(Path.GetDirectoryName(resultPath) ?? ".");
            File.WriteAllText(resultPath, JsonUtility.ToJson(record, true));
            if (summary.result != BuildResult.Succeeded)
                throw new InvalidOperationException($"{target} build {summary.result} with {summary.totalErrors} errors.");
            return $"{target} build {record.version} ({record.build}) in {record.minutes} min";
        }

        private static string SafeName(string name)
        {
            foreach (char c in Path.GetInvalidFileNameChars())
                name = name.Replace(c, '_');
            return string.IsNullOrWhiteSpace(name) ? "Game" : name;
        }
    }
}
