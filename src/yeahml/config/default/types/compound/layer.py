import importlib

from yeahml.build.components.activation import configure_activation
from yeahml.build.components.constraint import configure_constraint
from yeahml.build.components.initializer import configure_initializer
from yeahml.build.components.regularizer import configure_regularizer

# TODO: this should be moved
from yeahml.build.layers.config import (
    NOTPRESENT,
    return_available_layers,
    return_layer_defaults,
)
from yeahml.config.default.types.base_types import (
    categorical,
    custom_source_config,
    default_config,
    list_of_categorical,
    list_of_numeric,
    numeric,
)
from yeahml.config.default.types.compound.data import data_in_spec

SPECIAL_OPTIONS = [
    ("kernel_regularizer", configure_regularizer),
    ("bias_regularizer", configure_regularizer),
    ("activity_regularizer", configure_regularizer),
    ("activation", configure_activation),
    ("kernel_initializer", configure_initializer),
    ("bias_initializer", configure_initializer),
    ("kernel_constraint", configure_constraint),
    ("bias_constraint", configure_constraint),
]


class layer_base_config:
    def __init__(self, layer_type=None, layer_source=None):
        if layer_type is None:
            raise ValueError("layer_type is not defined")
        else:

            # get function type and function information:
            # this outter if/else is for determining whether to obtain the layer
            # information from a source file, or from the keras api -- there are
            # no checks here
            if layer_source:
                layer_source = layer_source.replace("/", ".")
                if layer_source.endswith(".py"):
                    import_source = layer_source.rstrip("py").rstrip(".")
                custom_mod = importlib.import_module(f"{import_source}")

                try:
                    custom_func = custom_mod.__dict__[f"{layer_type}"]
                except AttributeError:
                    # NOTE: had a bad time with a list comp here so opted for a filter
                    names = list(
                        filter(lambda x: not x.startswith("_"), dir(custom_mod))
                    )
                    # names = [
                    #     n if not n.startswith("_") else pass for n in dir(custom_mod)
                    # ]
                    raise AttributeError(
                        f"custom layer named {layer_type} not found in {import_source} -- found: {names}. All names found {dir(custom_mod)}"
                    )
                self.str = f"{layer_type}"
                fn_dict = return_layer_defaults(custom_func)
            else:
                self.str = categorical(
                    required=True,
                    is_type=str,
                    is_in_list=return_available_layers().keys(),
                    description=(
                        "string defining the layer type of the indicated layer\n"
                        " > e.g. model:layers:conv_1:type: 'conv2d'"
                    ),
                )(layer_type)

                fn_dict = return_layer_defaults(self.str)
            # fn_dict:
            # {
            #     "func": func,
            #     "func_args": func_args,
            #     "func_defaults": func_defaults,
            # }
            self.func = fn_dict["func"]
            self.func_args = fn_dict["func_args"]
            self.func_defaults = fn_dict["func_defaults"]

    def __str__(self):
        return str(self.__class__) + ": " + str(self.__dict__)

    def __call__(self):
        return self.__dict__


def convert_to_list(raw_str):
    raw_str = raw_str.rstrip(")([]")
    raw_str = raw_str.lstrip(")([]")
    split_vals = raw_str.split(",")
    split_ints = [int(string) for string in split_vals]
    return split_ints


class layer_options_config:
    def __init__(self, func_args=None, func_defaults=None, user_args=None):
        # ensure user args is a subset of func_args
        self.user_vals = []
        if user_args:
            special_options_names = [v[0] for v in SPECIAL_OPTIONS]
            for i, arg_name in enumerate(func_args):
                # there are 'special' options... these are parameters that
                # accept classes/functions
                if arg_name in user_args:
                    if arg_name in special_options_names:
                        # arg_v = None
                        ind = special_options_names.index(arg_name)
                        special_func = SPECIAL_OPTIONS[ind][1]
                        if arg_name in user_args:
                            arg_v = user_args[arg_name]
                            if isinstance(arg_v, dict):
                                # extract useful components
                                try:
                                    func_type = arg_v["type"]
                                except KeyError:
                                    raise ValueError(
                                        f"Function for {arg_name} is not specified as a type:[<insert_type_here>]"
                                    )
                                try:
                                    func_opts = arg_v["options"]
                                except KeyError:
                                    func_opts = None

                                # use special functions
                                # TODO: make sure the special_func accepts this signature
                                arg_v = special_func(func_type, func_opts)
                            else:
                                raise TypeError(
                                    f"unable to create {arg_name} with options {arg_v} - a dictionary (with :type) is required"
                                )
                    else:
                        arg_v = user_args[arg_name]

                else:
                    arg_v = func_defaults[i]
                    if type(arg_v) == type(NOTPRESENT):
                        raise ValueError(
                            f"arg value for {arg_name} is not specified, but is required to be specified"
                        )

                # TODO: I'm not sure this "_shape" will always be true in that
                # it requires a list of ints.. also, consider tuple v list.
                exclude_names = ["noise_shape"]
                if arg_name.endswith("_shape"):
                    if arg_name not in exclude_names:
                        arg_v = convert_to_list(arg_v)

                self.user_vals.append(arg_v)
            # sanity check
            assert len(self.user_vals) == len(
                func_defaults
            ), f"user vals not set correctly"
        else:
            # no options are specified, but some arguments require it
            for i, arg_default in enumerate(func_defaults):
                if type(arg_default) == type(NOTPRESENT):
                    raise ValueError(
                        f"arg value for {func_args[i]} is not specified, but is required to be specified"
                    )

    def __str__(self):
        return str(self.__class__) + ": " + str(self.__dict__)

    def __call__(self):
        return self.__dict__


class layer_config:
    def __init__(
        self,
        layer_type=None,
        source=None,
        layer_options=None,
        layer_in_name=None,
        startpoint=False,
        endpoint=False,
    ):

        self.source = custom_source_config(
            default_value=None, required=False, is_type=str
        )(source)

        self.layer_base = layer_base_config(layer_type, self.source)()

        self.options = layer_options_config(
            func_args=self.layer_base["func_args"],
            func_defaults=self.layer_base["func_defaults"],
            user_args=layer_options,
        )()
        self.layer_in_name = list_of_categorical(
            default_value=None,
            required=True,
            is_type=str,
            description=(
                "name of the input to the current layer (as a string or list of strings)\n"
                " > e.g. model:layers:dense_2:in_name: 'dense_1'"
            ),
        )(layer_in_name)
        self.startpoint = startpoint
        self.endpoint = endpoint

    def __str__(self):
        return str(self.__class__) + ": " + str(self.__dict__)

    def __call__(self):
        return self.__dict__


class layers_parser:
    def __init__(self):
        pass

    def __str__(self):
        return str(self.__class__) + ": " + str(self.__dict__)

    def __call__(self, model_spec_dict):

        out_dict = {}
        prev_layer_name = None
        if isinstance(model_spec_dict, dict):
            for k, d in model_spec_dict.items():
                try:
                    layer_in_name = d["in_name"]
                except KeyError:
                    layer_in_name = prev_layer_name
                if not layer_in_name:
                    raise ValueError(
                        f"Current layer ({k}) does not have an input layer (:in_name) specified. If this is the first layer, you may consider specifying the name of data from the dataset prefixed with `data_`. i.e. in_name: data_<feature_a>"
                    )

                try:
                    layer_is_startpoint = d["startpoint"]
                except KeyError:
                    layer_is_startpoint = False

                try:
                    layer_is_endpoint = d["endpoint"]
                except KeyError:
                    layer_is_endpoint = False

                try:
                    user_options = d["options"]
                except KeyError:
                    user_options = None

                try:
                    custom_source = d["source"]
                except KeyError:
                    custom_source = None

                try:
                    out_dict[k] = layer_config(
                        layer_type=d["type"],
                        source=custom_source,
                        layer_options=user_options,
                        layer_in_name=layer_in_name,
                        startpoint=layer_is_startpoint,
                        endpoint=layer_is_endpoint,
                    )()
                    # increment layer
                    prev_layer_name = k
                except KeyError:
                    raise KeyError(
                        f"layer_config '[key={k}, dict={d}]' was expecting to have k = 'name_string' and dict to contain `:type`"
                    )
        else:
            raise ValueError(
                f"{data_in_spec} is type {type(data_in_spec)} not type {type({})}"
            )

        return out_dict
