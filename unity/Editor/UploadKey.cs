using System;
using System.IO;
using System.Runtime.InteropServices;
using UnityEditor;

namespace ReleaseDesk.Editor
{
    /// <summary>
    /// Signs one Android release build with the upload key. The password is read from Windows Credential Manager
    /// inside the Editor, used for this build only and never written to ProjectSettings or any log; the previous
    /// keystore settings are restored afterwards.
    /// </summary>
    internal sealed class UploadKey : IDisposable
    {
        private readonly bool useCustom;
        private readonly string keystoreName;
        private readonly string aliasName;

        public UploadKey(string keystorePath, string credential, string alias)
        {
            if (!File.Exists(keystorePath))
                throw new InvalidOperationException("Upload keystore not found: " + keystorePath);
            string password = ReadPassword(credential);
            if (string.IsNullOrEmpty(password))
                throw new InvalidOperationException("No password for " + credential + " in Windows Credential Manager.");
            useCustom = PlayerSettings.Android.useCustomKeystore;
            keystoreName = PlayerSettings.Android.keystoreName;
            aliasName = PlayerSettings.Android.keyaliasName;
            PlayerSettings.Android.useCustomKeystore = true;
            PlayerSettings.Android.keystoreName = keystorePath;
            PlayerSettings.Android.keystorePass = password;
            PlayerSettings.Android.keyaliasName = alias;
            PlayerSettings.Android.keyaliasPass = password;
        }

        public void Dispose()
        {
            PlayerSettings.Android.keystorePass = "";
            PlayerSettings.Android.keyaliasPass = "";
            PlayerSettings.Android.keystoreName = keystoreName;
            PlayerSettings.Android.keyaliasName = aliasName;
            PlayerSettings.Android.useCustomKeystore = useCustom;
        }

        [StructLayout(LayoutKind.Sequential, CharSet = CharSet.Unicode)]
        private struct Credential
        {
            public int Flags;
            public int Type;
            public string TargetName;
            public string Comment;
            public System.Runtime.InteropServices.ComTypes.FILETIME LastWritten;
            public int CredentialBlobSize;
            public IntPtr CredentialBlob;
            public int Persist;
            public int AttributeCount;
            public IntPtr Attributes;
            public string TargetAlias;
            public string UserName;
        }

        [DllImport("advapi32.dll", EntryPoint = "CredReadW", CharSet = CharSet.Unicode, SetLastError = true)]
        private static extern bool CredRead(string target, int type, int flags, out IntPtr credential);

        [DllImport("advapi32.dll")]
        private static extern void CredFree(IntPtr buffer);

        private static string ReadPassword(string target)
        {
            if (Environment.OSVersion.Platform != PlatformID.Win32NT)
                throw new PlatformNotSupportedException("Upload key passwords are read from Windows Credential Manager.");
            const int generic = 1;
            if (!CredRead(target, generic, 0, out IntPtr handle))
                return null;
            try
            {
                var credential = Marshal.PtrToStructure<Credential>(handle);
                return credential.CredentialBlobSize > 0
                    ? Marshal.PtrToStringUni(credential.CredentialBlob, credential.CredentialBlobSize / 2)
                    : null;
            }
            finally
            {
                CredFree(handle);
            }
        }
    }
}
