#!/usr/bin/python
# -*- coding: utf-8 -*-

from pyspark import SparkConf, SparkContext


conf = SparkConf()
sc = SparkContext(appName="WordCount", conf=conf)

sc.textFile("s3://dimajix-training/data/alice").flatMap(lambda x: x.split()).filter(
    lambda x: x != ""
).map(lambda x: (x, 1)).reduceByKey(lambda x, y: x + y).sortBy(
    lambda x: x[1], ascending=False
).saveAsTextFile(
    "alice_wordcount"
)
