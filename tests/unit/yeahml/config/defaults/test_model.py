import pytest
import tensorflow as tf

from yeahml.build.layers.config import NOTPRESENT
from yeahml.config.default.default_config import DEFAULT_CONFIG
from yeahml.config.default.util import parse_default

"""
layers:
  dense_1:
    type: 'dense'
    options:
      units: 16
  dense_2:
    type: 'dense'
    options:
      units: 8
      activation:
        type: 'linear'
  dense_3_output:
    type: 'dense'
    options:
      units: 1
      activation:
        type: 'linear'
"""

# TODO: test options
# NOTE: multiple of the same name would need to be caught before here since the
# type is a dict and the same name will overwrite the current value
ex_config = {
    # ----- REQUIRED
    # missing
    "minimal_00": (
        {
            "model": {
                "name": "some_model",
                "start_fresh": True,
                "layers": {
                    "dense_1": {
                        "type": "dense",
                        "options": {
                            "units": "16",
                            "kernel_initializer": {"type": "glorotnormal"},
                            "bias_regularizer": {"type": "l2", "options": {"l2": 0.3}},
                            "activation": {"type": "elu"},
                        },
                        "in_name": "jack",
                    },
                    "bn_1": {
                        "type": "batchnormalization",
                        "options": None,
                        "in_name": "dense_1",
                    },
                    "dense_2": {
                        "type": "dense",
                        "options": {
                            "units": "16",
                            "kernel_initializer": {"type": "glorotnormal"},
                            "bias_regularizer": {"type": "l2", "options": {"l2": 0.3}},
                        },
                    },
                },
            }
        },
        {
            "name": "some_model",
            "start_fresh": True,
            "layers": {
                "dense_1": {
                    "layer_base": {
                        "str": "dense",
                        "func": tf.keras.layers.Dense,
                        "func_args": [
                            "units",
                            "activation",
                            "use_bias",
                            "kernel_initializer",
                            "bias_initializer",
                            "kernel_regularizer",
                            "bias_regularizer",
                            "activity_regularizer",
                            "kernel_constraint",
                            "bias_constraint",
                            "trainable",
                            "name",
                            "dtype",
                            "dynamic",
                        ],
                        "func_defaults": [
                            NOTPRESENT,
                            None,
                            True,
                            "glorot_uniform",
                            "zeros",
                            None,
                            None,
                            None,
                            None,
                            None,
                            True,
                            None,
                            None,
                            False,
                        ],
                    },
                    "options": {
                        "user_vals": [
                            "16",
                            tf.keras.activations.elu,
                            True,
                            tf.keras.initializers.GlorotNormal(),
                            "zeros",
                            None,
                            tf.keras.regularizers.l2(
                                l2=0.3
                            ),  # TODO: this isn't checked for options
                            None,
                            None,
                            None,
                            True,
                            None,
                            None,
                            False,
                        ]
                    },
                    "layer_in_name": ["jack"],
                },
                "bn_1": {
                    "layer_base": {
                        "str": "batchnormalization",
                        "func": tf.keras.layers.BatchNormalization,
                        "func_args": [
                            "axis",
                            "momentum",
                            "epsilon",
                            "center",
                            "scale",
                            "beta_initializer",
                            "gamma_initializer",
                            "moving_mean_initializer",
                            "moving_variance_initializer",
                            "beta_regularizer",
                            "gamma_regularizer",
                            "beta_constraint",
                            "gamma_constraint",
                            "renorm",
                            "renorm_clipping",
                            "renorm_momentum",
                            "fused",
                            "trainable",
                            "virtual_batch_size",
                            "adjustment",
                            "name",
                            "trainable",
                            "name",
                            "dtype",
                            "dynamic",
                        ],
                        "func_defaults": [
                            -1,
                            0.99,
                            0.001,
                            True,
                            True,
                            "zeros",
                            "ones",
                            "zeros",
                            "ones",
                            None,
                            None,
                            None,
                            None,
                            False,
                            None,
                            0.99,
                            None,
                            True,
                            None,
                            None,
                            None,
                            True,
                            None,
                            None,
                            False,
                        ],
                    },
                    "options": {"user_vals": []},
                    "layer_in_name": ["dense_1"],
                },
                "dense_2": {
                    "layer_base": {
                        "str": "dense",
                        "func": tf.keras.layers.Dense,
                        "func_args": [
                            "units",
                            "activation",
                            "use_bias",
                            "kernel_initializer",
                            "bias_initializer",
                            "kernel_regularizer",
                            "bias_regularizer",
                            "activity_regularizer",
                            "kernel_constraint",
                            "bias_constraint",
                            "trainable",
                            "name",
                            "dtype",
                            "dynamic",
                        ],
                        "func_defaults": [
                            NOTPRESENT,
                            None,
                            True,
                            "glorot_uniform",
                            "zeros",
                            None,
                            None,
                            None,
                            None,
                            None,
                            True,
                            None,
                            None,
                            False,
                        ],
                    },
                    "options": {
                        "user_vals": [
                            "16",
                            None,
                            True,
                            tf.keras.initializers.GlorotNormal(),
                            "zeros",
                            None,
                            tf.keras.regularizers.l2(
                                l2=0.3
                            ),  # TODO: this isn't checked for options
                            None,
                            None,
                            None,
                            True,
                            None,
                            None,
                            False,
                        ]
                    },
                    # test that prev layer information is used here
                    "layer_in_name": ["bn_1"],
                },
            },
        },
    )
}


@pytest.mark.parametrize(
    "config,expected", ex_config.values(), ids=list(ex_config.keys())
)
def test_default(config, expected):
    """test parsing of model"""
    if isinstance(expected, dict):
        formatted_config = parse_default(config["model"], DEFAULT_CONFIG["model"])
        try:
            assert expected == formatted_config
        except AssertionError:
            for k, d in formatted_config["layers"].items():
                for opt in ["user_vals"]:
                    try:
                        assert (
                            d["options"][opt] is expected["layers"][k]["options"][opt]
                        ), f"layer {k} does not have matching {opt}"
                    except AssertionError:
                        for i, a in enumerate(d["options"][opt]):
                            b = expected["layers"][k]["options"][opt][i]
                            try:
                                assert (
                                    a is b
                                ), f"layer {k} does not have matching {opt} for {a} != {b}"
                            except AssertionError:
                                if issubclass(
                                    type(b), tf.keras.regularizers.Regularizer
                                ):
                                    # TODO: implement more in depth check
                                    assert issubclass(
                                        type(a), tf.keras.regularizers.Regularizer
                                    )
                                elif issubclass(
                                    type(b), tf.keras.initializers.Initializer
                                ):
                                    # TODO: implement more in depth check
                                    assert issubclass(
                                        type(a), tf.keras.initializers.Initializer
                                    )
                                else:
                                    assert (
                                        a == b
                                    ), f"{opt} in layer {k} does not match: {a} != {b}"
                for opt in ["func", "func_args", "func_defaults"]:
                    assert (
                        d["layer_base"][opt] == expected["layers"][k]["layer_base"][opt]
                    ), f"layer {k} does not have matching {opt}"
                for opt in ["layer_in_name"]:
                    # print(d[opt])
                    assert (
                        d[opt] == expected["layers"][k][opt]
                    ), f"layer {k} does not have matching {opt}"

    elif isinstance(expected, ValueError):
        with pytest.raises(ValueError):
            formatted_config = parse_default(config["model"], DEFAULT_CONFIG["model"])
    elif isinstance(expected, TypeError):
        with pytest.raises(TypeError):
            formatted_config = parse_default(config["model"], DEFAULT_CONFIG["model"])
