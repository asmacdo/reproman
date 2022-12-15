# we do not need anything from those APT sources, and they
# often fail, disable!
sed -i -e '/mongodb/d' /etc/apt/sources.list /etc/apt/sources.list.d/*list
# The ultimate one-liner setup for NeuroDebian repository
bash <(wget -q -O- http://neuro.debian.net/_files/neurodebian-travis.sh)
apt-get update -qq
apt-get install eatmydata -y
# So we could test under sudo -E with PATH pointing to
# installed location
sed -i -e 's/^Defaults.*secure_path.*$//' /etc/sudoers
# sqlite3: for SVN tests (SVNRepoShim._ls_files_command())
# parallel: for concurrent jobs with local orchestrator
eatmydata apt-get install sqlite3 parallel singularity-container -y
git config --global user.email "reproman@repronim.org"
git config --global user.name "ReproMan Tester"
# Set defaultBranch to avoid polluting output with repeated
# warnings, and set it to something other than "master" to
# check that no functionality hard codes the default branch.
git config --global init.defaultBranch rman-default-test-branch
