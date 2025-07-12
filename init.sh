apt update
apt install cpanminus

# 1. 自我更新 cpanm
cpanm App::cpanminus

# 2. 清除 cpanmetadb 的缓存
#    注意：这个命令会删除 ~/.cpanm/cpanmetadb.json 文件
rm -f ~/.cpanm/cpanmetadb.json 

cd /mnt/workspace/defects4j
cpanm --installdeps .

cpanm Perl::Critic

cpanm JSON::Parse
cpanm DBI
cpanm DBD::CSV
cpanm String::Interpolate
cpanm JSON


apt install openjdk-11-jdk -y
apt install subversion -y
pip install openai tiktoken javalang
