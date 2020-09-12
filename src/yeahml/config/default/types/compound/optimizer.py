from yeahml.build.components.optimizer import return_available_optimizers
from yeahml.config.default.types.base_types import (
    categorical,
    list_of_categorical,
    numeric,
)
from yeahml.config.default.types.param_types import parameter_config


class optimizer_config:
    def __init__(
        self, opt_type=None, opt_options=None, opt_name=None, opt_objectives=None
    ):

        # TODO: there are consistency issues here with the names of classes
        # and where the types are being created/checked

        self.type = categorical(
            default_value=None,
            required=True,
            is_in_list=return_available_optimizers(),
            to_lower=True,
            description=(
                "The type of optimizer being used\n"
                " > e.g. optimize:optimizers:'name':type: 'adam'"
            ),
        )(opt_type)

        self.options = parameter_config(
            known_dict={
                "learning_rate": numeric(
                    default_value=None,
                    required=True,
                    is_type=float,
                    description=(
                        "The learning rate for a specified optimizer\n"
                        " > e.g. optimize:optimizers:'name':options:learning_rate 0.001"
                    ),
                )
            }
        )(opt_options)

        # TODO: in a secondary check, we need to ensure the losses specified
        # are valid+included
        self.objectives = list_of_categorical(
            default_value=None,
            required=True,
            to_lower=True,
            description=(
                "The objective for a specified optimizer to optimize\n"
                " > e.g. optimize:optimizers:'name':objectives: ['mnist_objective']"
            ),
        )(opt_objectives)

    def __str__(self):
        return str(self.__class__) + ": " + str(self.__dict__)

    def __call__(self):
        return self.__dict__


class optimizers_parser:
    def __init__(self):
        pass

    def __str__(self):
        return str(self.__class__) + ": " + str(self.__dict__)

    def __call__(self, optimizers_spec_dict):
        # TODO: this should be moved to the __init__
        if isinstance(optimizers_spec_dict, dict):
            temp_dict = {}
            for k, d in optimizers_spec_dict.items():

                optimizer_name = categorical(
                    default_value=None,
                    required=True,
                    is_type=str,
                    to_lower=False,
                    description=(
                        "The name of the optimizer \n"
                        " > e.g. optimize:optimizers: 'mnist_opt'"
                    ),
                )(k)

                try:
                    opt_type = d["type"]
                except:
                    opt_type = None

                try:
                    opt_options = d["options"]
                except:
                    opt_options = None

                try:
                    opt_objectives = d["objectives"]
                except:
                    opt_objectives = None

                conf = optimizer_config(
                    opt_type=opt_type,
                    opt_options=opt_options,
                    opt_objectives=opt_objectives,
                )()
                temp_dict[k] = conf

        else:
            raise ValueError(
                f"optimizers_spec_dict ({optimizers_spec_dict}) is type {type(optimizers_spec_dict)} not type {type({})}"
            )
        return temp_dict
