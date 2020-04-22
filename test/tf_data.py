import numpy as np
import glob
import multiprocessing
import os

import tensorflow as tf
from tf_model import load_one_file

#save this many events in one TFRecord file
NUM_EVENTS_PER_TFR = 100

def parse_args():
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--target", type=str, choices=["cand", "gen"], help="Regress to PFCandidates or GenParticles", default="cand")
    args = parser.parse_args()
    return args

def chunks(lst, n):
    """Yield successive n-sized chunks from lst."""
    for i in range(0, len(lst), n):
        yield lst[i:i + n]

#https://stackoverflow.com/questions/47861084/how-to-store-numpy-arrays-as-tfrecord
def _bytes_feature(value):
    """Returns a bytes_list from a string / byte."""
    if isinstance(value, type(tf.constant(0))): # if value ist tensor
        value = value.numpy() # get value of tensor
    return tf.train.Feature(bytes_list=tf.train.BytesList(value=[value]))

def _parse_tfr_element(element):
    parse_dic = {
        'X': tf.io.FixedLenFeature([], tf.string),
        'y': tf.io.FixedLenFeature([], tf.string),
        'w': tf.io.FixedLenFeature([], tf.string),
    }
    example_message = tf.io.parse_single_example(element, parse_dic)

    X = example_message['X']
    arr_X = tf.io.parse_tensor(X, out_type=tf.float32)
    y = example_message['y']
    arr_y = tf.io.parse_tensor(y, out_type=tf.float32)
    w = example_message['w']
    arr_w = tf.io.parse_tensor(w, out_type=tf.float32)

    #https://github.com/tensorflow/tensorflow/issues/24520#issuecomment-577325475
    arr_X.set_shape(tf.TensorShape((None, None)))
    arr_y.set_shape(tf.TensorShape((None, None)))
    arr_w.set_shape(tf.TensorShape((None, )))

    return arr_X, arr_y, arr_w

def serialize_X_y_w(writer, X, y, w):
    feature = {
        'X': _bytes_feature(tf.io.serialize_tensor(X)),
        'y': _bytes_feature(tf.io.serialize_tensor(y)),
        'w': _bytes_feature(tf.io.serialize_tensor(w))
    }
    sample = tf.train.Example(features=tf.train.Features(feature=feature))
    writer.write(sample.SerializeToString())

def serialize_chunk(args):
    path, files, ichunk, target = args
    out_filename = os.path.join(path, "chunk_{}.tfrecords".format(ichunk))
    writer = tf.io.TFRecordWriter(out_filename)
    Xs = []
    ys = []
    ws = []

    for fi in files:
        X, y, ycand = load_one_file(fi)
        Xs += [X]
        if target == "cand":
            ys += [ycand]
        elif target == "gen":
            ys += [ycand]
        else:
            raise Exception("Unknown target")

    uniq_vals, uniq_counts = np.unique(np.concatenate([y[:, 0] for y in ys]), return_counts=True)
    for i in range(len(ys)):
        w = np.ones(len(ys[i]), dtype=np.float32)
        for uv, uc in zip(uniq_vals, uniq_counts):
            w[ys[i][:, 0]==uv] = 1.0/uc
        ids = ys[i][:, 0]

        w[ids==0] *= w[ids!=0].sum()/w[ids==0].sum()
        #w *= len(ys[i])

        ws += [w]

    for X, y, w in zip(Xs, ys, ws):
        serialize_X_y_w(writer, X, y, w)

    writer.close()

if __name__ == "__main__":
    args = parse_args()
    tf.config.experimental_run_functions_eagerly(True)

    filelist = sorted(glob.glob("data/TTbar_14TeV_TuneCUETP8M1_cfi/raw/*.pkl"))
    path = "data/TTbar_14TeV_TuneCUETP8M1_cfi/tfr/{}".format(args.target)

    if not os.path.isdir(path):
        os.makedirs(path)

    pars = []
    for ichunk, files in enumerate(chunks(filelist, NUM_EVENTS_PER_TFR)):
        pars += [(path, files, ichunk, args.target)]
    print(len(pars))
    pool = multiprocessing.Pool(20)
    pool.map(serialize_chunk, pars)
 
    #tfr_dataset = tf.data.TFRecordDataset(glob.glob("test_*.tfrecords"))
    #dataset = tfr_dataset.map(_parse_tfr_element)
    #ds_train = dataset.take(15000)
    #ds_test = dataset.skip(15000).take(5000)
