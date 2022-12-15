python3.7 -m pip install -e /home/austin/reproman[tests]
python3.7 -m pip install chardet
cd /home/austin/reproman
# TODO(asmacdo) stop asking questions
# ./tools/ci/install_condor condor
# ./neurodebian-travish.sh -y
./workflow-setup.sh
