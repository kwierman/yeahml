import tensorflow as tf
import numpy as np


def build_hidden_block(X, MCd: dict, ACd: dict):
    # in: X
    # out: last layer before logits

    act_fn = tf.nn.elu

    with tf.name_scope("hidden"):
        # TODO: hidden layer logic
        h_1 = tf.layers.conv2d(
            X,
            filters=32,
            kernel_size=3,
            activation=act_fn,
            padding="SAME",
            strides=2,
            name="conv_1",
        )

        h_2 = tf.layers.conv2d(
            h_1,
            filters=64,
            kernel_size=3,
            activation=act_fn,
            padding="SAME",
            strides=2,
            name="conv_2",
        )

        h_3 = tf.layers.conv2d(
            h_2,
            filters=96,
            kernel_size=3,
            activation=act_fn,
            padding="SAME",
            strides=2,
            name="conv_3",
        )

        h_4 = tf.layers.max_pooling2d(
            h_3, pool_size=[2, 2], strides=2, name="max_pool_01"
        )

        h_5 = tf.layers.conv2d(
            h_4,
            filters=128,
            kernel_size=3,
            activation=act_fn,
            padding="SAME",
            strides=1,
            name="conv_4",
        )

        h_6 = tf.layers.conv2d(
            h_5,
            filters=192,
            kernel_size=3,
            activation=act_fn,
            padding="SAME",
            strides=1,
            name="conv_5",
        )

        last_shape = int(np.prod(h_6.get_shape()[1:]))
        h_out_flat = tf.reshape(h_6, shape=[-1, last_shape])

        h_10 = tf.layers.dense(h_out_flat, 256, name="layer_01", activation=act_fn)
        h_11 = tf.layers.dense(h_10, 64, name="layer_02", activation=act_fn)
        h_12 = tf.layers.dense(h_11, 16, name="layer_03", activation=act_fn)

        last = h_12

    return last