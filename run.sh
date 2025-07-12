export PATH=$PATH:/mnt/workspace/defects4j/framework/bin

export JAVA_HOME=/usr/lib/jvm/java-11-openjdk-amd64

python Generation/repair.py --folder Results/test --lang Java --dataset defects4j-1.2-single-line --few_shot 1 --chain_length 3 --total_tries 200 --assertion_line  --suffix