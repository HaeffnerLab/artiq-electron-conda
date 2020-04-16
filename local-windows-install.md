Setting up Lattice's LabRAD + ARTIQ locally on Windows
==============
Before you start, if you have anything left over from a previous setup, go ahead and delete it. For example, you should delete:
  - `C:\LabRAD`, if it exists
  - Anything LabRAD or ARTIQ related under `C:\Repos` or `C:\Users\<username>`
  - Any shortcuts you may have for starting LabRAD or ARTIQ
  
Now follow these steps carefully to get the necessary Lattice LabRAD and ARTIQ components running on your Windows machine.

1. Install Anaconda, if you don't have it already, from:
https://repo.anaconda.com/archive/Anaconda3-2020.02-Windows-x86_64.exe.
Keep all the installation defaults, as some later parts of the setup depend on this.

2. Download this complete package of all the LabRAD and ARTIQ stuff you will need: 

    **[Lattice-LabRAD-ARTIQ-Windows-package](https://www.dropbox.com/sh/qe9fhxtldfolaqv/AADFkTKwL77O3U7sHsn5t9nIa?dl=1)**

    (It's about 900 MB, may take a little while.) Once this finishes downloading, unzip it somewhere convenient, maybe `C:\Artiq-Windows`.

3. After the Anaconda installation has finished, open an Anaconda Prompt
and run `conda-recreate-envs.bat` from the `C:\Artiq-Windows` folder.
This will take a while - it will delete any `artiq` or `labrad` conda environments you might have,
and recreate them from scratch. You can continue with the other steps while this is going.

4. Unzip the `LabRAD (unzip to C drive root).zip` file to `C:\`. This should create a `C:\LabRAD` folder.

5. Unzip the `Repos (unzip to user home folder).zip` to `C:\Users\<your_user_name>`.  This should create a number
of folders directly in your `C:\Users\<username>` folder:
    - `artiq`
    - `artiq-master`
    - `artiq-work`
    - `labrad`
    - `.labrad` (with a period)
      - This folder is important; it contains the full parameter vault. If you don't see it, ensure that "show hidden files" is enabled
      in your File Explorer settings.
      
    Also note that there are clones of several GitHub repos here, and if you install Git/GitHub tools on your machine you'll be able
    to sync these to pull any changes that have been pushed since you first set this up.

6. Open a command prompt and run `set-labrad-env-variables.bat` from the `C:\Artiq-Windows` folder.

7. Install Java Runtime if you don't have it already by running `Java Runtime 8u241 x86 (required for LabRAD).exe`
from the `C:\Artiq-Windows` folder. LabRAD requires this.

8. Double-click the `lab-artiq-putty.reg` file from the `C:\Artiq-Windows` folder.
This adds a PuTTy configuration file with tunnels that allow communication with the ARTIQ hardware in the lab.

9. Make sure that the Anaconda environment creation from step 3 completed successfully.

Running Lattice's LabRAD + ARTIQ locally on Windows
==============
After you've completed the above installation steps, here are the steps to get ARTIQ Dashboard running:
1. _(Optional, only if you want to run things on the real ARTIQ hardware)_ Connect to the lab tunnel: Open `PuTTy.exe` (you should have a copy in `C:\Artiq-Windows`),
load the "Haeffner Lab with Tunnels" profile, and click Open.
You'll have to login with a valid lab username and password, either yours or lab-user.
2. To start LabRAD and all necessary servers, run `C:\LabRAD\start_labrad.bat`. Wait a few seconds for this to complete.
3. To start the ARTIQ Master, run `C:\Users\<username>\artiq\artiq_master_start.bat`.
4. To start the ARTIQ Dashboard, run `C:\Users\<username>\artiq\artiq_dashboard_start.bat`.

After several seconds, the ARTIQ dashboard should load successfully. If you didn't connect to the lab tunnel, you'll see a bunch of error messages about being unable to communicate with the hardware, but these can be ignored.

Troubleshooting Common Issues
==============
**Issue:** If your computer unexpectedly shuts down or crashes while ARTIQ is running, you may see a failure
the next time you try to start ARTIQ Master, due to a corrupted `dataset_db.pyon` file.  
**Fix:** Delete the file at `C:\Users\<username>\artiq-master\dataset_db.pyon`. It will be automatically recreated on the next run.
