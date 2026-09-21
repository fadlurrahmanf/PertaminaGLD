using System;
using System.IO;
using System.IO.Compression;

internal static class Program
{
    private static int Main(string[] args)
    {
        try
        {
            if (args.Length == 2 && args[0] == "-Z1")
            {
                using (ZipArchive archive = ZipFile.OpenRead(args[1]))
                {
                    foreach (ZipArchiveEntry entry in archive.Entries)
                    {
                        Console.Out.WriteLine(entry.FullName);
                    }
                }
                return 0;
            }

            if (args.Length == 3 && args[0] == "-p")
            {
                using (ZipArchive archive = ZipFile.OpenRead(args[1]))
                {
                    ZipArchiveEntry entry = archive.GetEntry(args[2]);
                    if (entry == null)
                    {
                        Console.Error.WriteLine("Entry not found: " + args[2]);
                        return 3;
                    }

                    using (Stream input = entry.Open())
                    using (Stream output = Console.OpenStandardOutput())
                    {
                        input.CopyTo(output);
                    }
                }
                return 0;
            }

            Console.Error.WriteLine("Unsupported unzip arguments.");
            return 2;
        }
        catch (Exception ex)
        {
            Console.Error.WriteLine(ex.Message);
            return 1;
        }
    }
}
