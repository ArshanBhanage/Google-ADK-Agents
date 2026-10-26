# Foundation container

`make check-container` builds the locked API as UID 10001. The image contains only
code and locked dependencies; .env files and local data are excluded. The local
image is not a cloud deployment. Persistent shared sessions, secrets, private
AlloyDB/Toolbox networking and deployment controls are future gated work.
