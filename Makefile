
# TODO(asmacdo) UID GID were'nt getting set correctly
build:
	docker build -t dev-env \
	    -f Dockerfile-debian \
		.

# --build-arg IMAGE=ubuntu:18.04 \



ssh:
	docker run -it --rm --name dev-env\
		-v $PWD:/home/$USER/reproman \
		-v /var/run/docker.sock:/var/run/docker.sock \
		-v /home/austin/dart/reproman:/home/austin/reproman \
		dev-env

