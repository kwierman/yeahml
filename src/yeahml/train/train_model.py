import pathlib
from typing import Any, Dict

import tensorflow as tf

from yeahml.log.yf_logging import config_logger  # custom logging
from yeahml.train.gradients.gradients import (
    get_apply_grad_fn,
    get_get_supervised_grads_fn,
    get_validation_step_fn,
    update_model_params,
)
from yeahml.train.inference import inference_dataset

# select which task to optimize
from yeahml.train.sample_tasks.objective import select_objective
from yeahml.train.sample_tasks.optimizer import select_optimizer
from yeahml.train.setup.datasets import get_datasets
from yeahml.train.setup.objectives import get_objectives
from yeahml.train.setup.paths import (
    create_model_run_path,
    create_model_training_paths,
    get_tb_writers,
)
from yeahml.train.setup.tracker.metric import (
    create_metric_trackers,
    update_metric_trackers,
)
from yeahml.train.setup.tracker.tracker import (
    create_joint_dict_tracker,
    record_joint_losses,
)
from yeahml.train.update_progress.tf_objectives import update_metric_objects
from yeahml.train.update_progress.tracker import (
    update_loss_trackers,
    update_metrics_tracking,
)
from yeahml.train.util import (
    convert_to_single_pass_iterator,
    get_losses_to_update,
    get_next_batch,
    re_init_iter,
)

from yeahml.train.setup.loop_dynamics import (  # obtain_optimizer_loss_mapping,; create_grouped_metrics,; map_in_config_to_objective,
    create_full_dict,
    get_optimizers,
)


# from yeahml.build.load_params_onto_layer import init_params_from_file  # load params


"""
this training logic will need to be cleaned up/refactored a few times, but for
now it is "working" as I hoped.

- create a single fn that accepts "train"/"val" and does the logic (the loops
  are ~the same) and accepts a ds that is of the appropriate size .take()
- simplify/standardize the `return_dict` -- also accept any batch_steps for
  logging + determining when to save params.
- the variable naming throughout this is super inconsistent and not always
  accurate, I intend to improve this over time
- I need to validate the metric/loss/joint logic. I've only tried the present
  case and I'm not sure it will generalize well yet
- tensorboard -- I'm waiting until the loop logic is cleaned up before writing
  to tb again
- early stopping
- save best params
- create a variable in the graph to keep track of the number of batch
  steps/epochs run (if run from a notebook) --- also allow for the passing of an
  epoch param so that if we want to only run ~n more epochs from the notebook we
  can
- I'll also need to ensure the tracking dict is persisted.

- could keep note of all extra tricky batches/instances after n epochs.
"""


"""
TODO: check that all metrics are accounted for.  If so. raise a not
implemented error -- presently the training loop is driven by the
optimizers (and as a result all objectives that have matching in_configs).
meaning, if a metric does not have a matching in_config, it will not be
evaluated.

# TODO: random -- check for nans in loss values

TODO: build best loss dict

TODO: ASSUMPTION: using optimizers sequentially. this may be:
- jointly, ordered: sequentially, or unordered: alternate/random

NOTE: I'm not sure looping on epochs makes sense as an outter layer
anymore.
TODO: is there a way to save a variable in the graph to keep track of
epochs (if multiple runs from a notebook?)

TODO: per batch/epoch/adaptive -- all open questions.

NOTE: this isn't perfect in that someone may care about the output of
something they are not directly optimizing.. I'd argue the current
workaround is to specify that metric with a dataset and associate it to a
particular optimizer (it will eval at the same time this optimizer is run)


"""


def log_model_params(tr_writer, g_train_step, model):
    with tr_writer.as_default():
        for v in model.variables:
            tf.summary.histogram(v.name.split(":")[0], v.numpy(), step=g_train_step)


def update_epoch_dict(
    obj_ds_to_epoch: Dict[str, Any],
    objective_name: str,
    dataset_name: str,
    split_name: str,
):
    """update num of iterations
    """
    try:
        obj_ds_to_epoch[objective_name][dataset_name][split_name] += 1
    except KeyError:
        # begin at 1 since it is initialized after being run
        tmp_dict = {objective_name: {dataset_name: {split_name: 1}}}
        obj_ds_to_epoch = {**obj_ds_to_epoch, **tmp_dict}
    return obj_ds_to_epoch


def determine_if_training(opt_obj_ds_to_training):

    # if a single is_training is found return True, else they are all false,
    # return false
    for opt_name, opt_to_training in opt_obj_ds_to_training.items():
        for obj_name, obj_to_training in opt_to_training.items():
            for ds_name, ds_to_training in obj_to_training.items():
                for split_name, is_training in ds_to_training.items():
                    if is_training:
                        return True

    return False


# def start_profiler(profile_path, profiling):
#     if not profiling:
#         tf.profiler.experimental.start(str(profile_path))


# def stop_profiler():
#     tf.profiler.experimental.stop()


def get_train_iter(dataset_iter_dict, cur_ds_name, split_name):
    cur_ds_iter_dict = dataset_iter_dict[cur_ds_name]
    if split_name not in cur_ds_iter_dict.keys():
        raise ValueError(
            f"{cur_in_conf['dataset']} does not have a {split_name} dataset"
        )
    cur_train_iter = cur_ds_iter_dict[split_name]
    return cur_train_iter


def train_model(
    model: Any, config_dict: Dict[str, Dict[str, Any]], datasets: dict = None
) -> Dict[str, Any]:

    # TODO: option to reinitialize model?

    # unpack configurations
    model_cdict: Dict[str, Any] = config_dict["model"]
    meta_cdict: Dict[str, Any] = config_dict["meta"]
    log_cdict: Dict[str, Any] = config_dict["logging"]
    data_cdict: Dict[str, Any] = config_dict["data"]
    hp_cdict: Dict[str, Any] = config_dict["hyper_parameters"]

    perf_cdict: Dict[str, Any] = config_dict["performance"]
    optim_cdict: Dict[str, Any] = config_dict["optimize"]

    return_dict = {}

    full_exp_path = (
        pathlib.Path(meta_cdict["yeahml_dir"])
        .joinpath(meta_cdict["data_name"])
        .joinpath(meta_cdict["experiment_name"])
        .joinpath(model_cdict["name"])
    )

    # build paths and obtain tb writers
    model_run_path = create_model_run_path(full_exp_path)
    # profile_path = model_run_path.joinpath("tf_logs").joinpath("profile")
    save_model_path, save_best_param_path = create_model_training_paths(model_run_path)
    tr_writer, v_writer = get_tb_writers(model_run_path)
    log_model_params(tr_writer, 0, model)

    logger = config_logger(model_run_path, log_cdict, "train")
    # get datasets
    # train_ds, val_ds = get_datasets(datasets, data_cdict, hp_cdict)
    dataset_dict = get_datasets(datasets, data_cdict, hp_cdict)

    # {optimizer_name: {"optimizer": tf.obj, "objective": [objective_name]}}
    optimizers_dict = get_optimizers(optim_cdict)

    # {objective_name: "in_config": {...}, "loss": {...}, "metric": {...}}
    objectives_dict = get_objectives(perf_cdict["objectives"], dataset_dict)

    # create a tf.function for applying gradients for each optimizer
    # TODO: I am not 100% about this logic for maping the optimizer to the
    #   apply_gradient fn... this needs to be confirmed to work as expected

    opt_to_validation_fn = {}
    opt_to_get_grads_fn, opt_to_app_grads_fn = {}, {}
    opt_to_steps = {}
    # used to determine which objectives to loop to calculate losses
    opt_to_loss_objectives = {}
    # used to determine which objectives to obtain to calculate metrics
    opt_to_metrics_objectives = {}

    for cur_optimizer_name, cur_optimizer_config in optimizers_dict.items():

        # TODO: check config to see which fn to get supervised/etc
        opt_to_get_grads_fn[cur_optimizer_name] = get_get_supervised_grads_fn()
        opt_to_app_grads_fn[cur_optimizer_name] = get_apply_grad_fn()
        opt_to_validation_fn[cur_optimizer_name] = get_validation_step_fn()
        opt_to_steps[cur_optimizer_name] = 0

        loss_objective_names = []
        metrics_objective_names = []
        for cur_objective in cur_optimizer_config["objectives"]:
            cur_objective_dict = objectives_dict[cur_objective]
            if "loss" in cur_objective_dict.keys():
                if cur_objective_dict["loss"]:
                    loss_objective_names.append(cur_objective)
            if "metrics" in cur_objective_dict.keys():
                if cur_objective_dict["metrics"]:
                    metrics_objective_names.append(cur_objective)
        opt_to_loss_objectives[cur_optimizer_name] = loss_objective_names
        opt_to_metrics_objectives[cur_optimizer_name] = metrics_objective_names

    # TODO: training_directive may be empty.
    # {
    #     "YEAHML_1": {"optimizers": ["YEAHML_0", "second_opt"], "operation": "&"},
    #     "YEAHML_0": {"optimizers": ["main_opt", "second_opt"], "operation": ","},
    # }
    # TODO: I will need to parse this to create a cleaner directive to follow
    # training_directive = optim_cdict["directive"]

    main_tracker_dict = create_full_dict(
        optimizers_dict=optimizers_dict,
        objectives_dict=objectives_dict,
        datasets_dict=dataset_dict,
    )

    dataset_iter_dict = convert_to_single_pass_iterator(dataset_dict)

    # TODO: create list order of directives to loop through -- I no longer know
    # that this is the best approach -- that is, this should be adaptive  and
    # learned during training and is related to  'how do I determine how "long"'
    # to go here... I think the 'right' answer is dependent on the losses (train
    # and val), but I think there is a short answer as well.
    # TODO: this needs to be driven by the directive, not just a walkthrough

    obj_ds_to_epoch = {}

    # initialize to True
    is_training = True
    num_training_ops = 0
    # a core issue here is that we're doing this entire loop for a single batch
    # NOTE: consider changing is_training to `switch_optimizer`

    # dictionary to keep track of what optimizers are still training on what
    # datasets
    opt_obj_ds_to_training = {}
    for opt_name, opt_conf in optimizers_dict.items():
        opt_obj_ds_to_training[opt_name] = {}
        loss_objective_names = opt_to_loss_objectives[opt_name]
        for ln in loss_objective_names:
            opt_obj_ds_to_training[opt_name][ln] = {}
            ds_name = objectives_dict[ln]["in_config"]["dataset"]
            # init all to True
            # currently there is only one ds per objective
            opt_obj_ds_to_training[opt_name][ln][ds_name] = {"train": True}

    # TODO: this is hardcoded for supervised settings
    # tf.keras models output the model outputs in a list, we need to get the
    # of each prediction we care about from that output to use in the loss
    # function
    # NOTE: I'm not sure how I feel about this -- is it better to have multiple
    # "tf.models" that share params (is that even possible) -- or is it better
    # to do this where it is one "tf.model"?
    if isinstance(model.output, list):
        MODEL_OUTPUT_ORDER = [n.name.split("/")[0] for n in model.output]
        objective_to_output_index = {}
        for obj_name, obj_dict in objectives_dict.items():
            try:
                pred_name = obj_dict["in_config"]["options"]["prediction"]
                out_index = MODEL_OUTPUT_ORDER.index(pred_name)
                objective_to_output_index[obj_name] = out_index
            except KeyError:
                # TODO: perform check later
                objective_to_output_index[obj_name] = None
    else:
        # TODO: this is hardcoded to assume supervised
        objective_to_output_index = {}
        for obj_name, obj_dict in objectives_dict.items():
            objective_to_output_index[obj_name] = None

    list_of_optimizers = list(optimizers_dict.keys())

    logger.info("START - training")
    while is_training:
        cur_optimizer_name = select_optimizer(list_of_optimizers)
        cur_optimizer_config = optimizers_dict[cur_optimizer_name]
        logger.info(f"optimizer: {cur_optimizer_name}")
        continue_optimizer = True
        # apply_current_optimizer is used to remain using a single optimizer

        # get optimizer
        cur_tf_optimizer = cur_optimizer_config["optimizer"]

        # loss
        # opt_name :loss :main_obj :ds_name :split_name :loss_name:desc_name
        # opt_name :metric :main_obj: ds_name :split_name :metric_name
        opt_tracker_dict = main_tracker_dict[cur_optimizer_name]

        # NOTE: if there are multiple objectives, they will be trained *jointly*
        # cur_optimizer_config:
        #   {'optimizer': <tf.opt{}>, 'objectives': ['main_obj']}
        # cur_apply_grad_fn = opt_name_to_gradient_fn[cur_optimizer_name]
        get_grads_fn = opt_to_get_grads_fn[cur_optimizer_name]
        apply_grads_fn = opt_to_app_grads_fn[cur_optimizer_name]

        # TODO: these should really be grouped by the in config (likely by
        # creating a hash) this allows us to group objectives by what
        # dataset their using so that we can reuse the same batch.
        # NOTE: for now, I'm saving the prediction and gt (if supervised) in
        # the grad_dict
        loss_objective_names = opt_to_loss_objectives[cur_optimizer_name]
        metrics_objective_names = opt_to_metrics_objectives[cur_optimizer_name]

        obj_to_grads = {}
        # TODO: the losses should be grouped by the ds used so that we only
        # obtain+run the batch once+ensuring it's the same batch
        loss_update_dict, update_metrics_dict = {}, {}
        while continue_optimizer:
            cur_objective = select_objective(loss_objective_names)
            logger.info(f"objective: {cur_objective}")
            continue_objective = True

            # TODO: next step -- continue_objective = True
            # each loss may be being optimized by data from different datasets
            cur_ds_name = objectives_dict[cur_objective]["in_config"]["dataset"]
            loss_conf = objectives_dict[cur_objective]["loss"]
            tf_train_loss_descs_to_update = get_losses_to_update(loss_conf, "train")

            cur_train_iter = get_train_iter(dataset_iter_dict, cur_ds_name, "train")

            while continue_objective:
                cur_batch = get_next_batch(cur_train_iter)
                if not cur_batch:

                    # dataset pass is complete
                    obj_ds_to_epoch = update_epoch_dict(
                        obj_ds_to_epoch, cur_objective, cur_ds_name, "train"
                    )

                    if (
                        obj_ds_to_epoch[cur_objective][cur_ds_name]["train"]
                        >= hp_cdict["epochs"]
                    ):

                        # update this particular combination to false -
                        # eventually this logic will be "smarter" i.e. not
                        # based entirely on number of epochs.
                        opt_obj_ds_to_training[cur_optimizer_name][cur_objective][
                            cur_ds_name
                        ]["train"] = False

                        # this objective is done. see if they're all done
                        is_training = determine_if_training(opt_obj_ds_to_training)

                        # TODO: this isn't the "best" way to handle this,
                        # ideally, we would decided (in an intelligent way) when
                        # we're done training a group of objectives by
                        # evaluating the loss curves
                        list_of_optimizers.remove(cur_optimizer_name)
                        logger.info(
                            f"{cur_optimizer_name} removed from list of opt. remaining: {list_of_optimizers}"
                        )
                        logger.info(f"is_training: {is_training}")
                        # TODO: determine whether to move to the next objective
                        # NOTE: currently, move to the next objective
                        if not is_training:
                            # need to break from all loops
                            continue_optimizer = False
                            continue_objective = False

                        # TODO: there is likely a better way to handle the case
                        # where we have reached the 'set' number of epochs for
                        # this problem

                    # the original dict is updated here in case another dataset
                    # needs to use the datset iter -- this could likely be
                    # optimized, but the impact would be minimal right now
                    cur_train_iter = re_init_iter(cur_ds_name, "train", dataset_dict)
                    dataset_iter_dict[cur_ds_name]["train"] = cur_train_iter

                    logger.info(
                        f"epoch {cur_objective} - {cur_ds_name} {'train'}:"
                        f" {obj_ds_to_epoch[cur_objective][cur_ds_name]['train']}"
                    )

                    # perform validation after each pass through the training
                    # dataset
                    # NOTE: the location of this 'validation' may change
                    # TODO: there is an error here where the first objective
                    # will be validated on the last epoch and then one more
                    # time.
                    # TODO: ensure the metrics are reset
                    #  iterate validation after iterating entire training..
                    # this will/should change to update on a set frequency --
                    # also, maybe we don't want to run the "full" validation,
                    # only a (random) subset?

                    # validation pass
                    cur_val_update = inference_dataset(
                        model,
                        loss_objective_names,
                        metrics_objective_names,
                        dataset_iter_dict,
                        opt_to_validation_fn[cur_optimizer_name],
                        opt_tracker_dict,
                        cur_objective,
                        cur_ds_name,
                        dataset_dict,
                        opt_to_steps[cur_optimizer_name],
                        num_training_ops,
                        objective_to_output_index,
                        objectives_dict,
                        v_writer,
                        logger,
                        split_name="val",
                    )

                    # log params used during validation in other location
                    log_model_params(v_writer, num_training_ops, model)

                    # TODO: has run entire ds -- for now, time to break out of
                    # this ds eventually, something smarter will need to be done
                    # here in the training loop, not just after an epoch
                    continue_objective = False

                else:

                    grad_dict = get_grads_fn(
                        model,
                        cur_batch,
                        loss_conf["object"],
                        objective_to_output_index[cur_objective],
                        tf_train_loss_descs_to_update,
                    )
                    # grad_dict contains {
                    #     "gradients": grads,
                    #     "predictions": prediction,
                    #     "final_loss": final_loss,
                    #     "losses": loss,
                    # }

                    # TODO: see note above about ensuring the same batch is used for
                    # losses with the same dataset specified
                    opt_to_steps[cur_optimizer_name] += cur_batch[0].shape[0]
                    num_training_ops += 1
                    # if num_training_ops > 5:
                    #     start_profiler(profile_path, profiling)
                    # elif num_training_ops > 10:
                    #     stop_profiler()

                    # TODO: currently this only stores the last grad dict per objective
                    obj_to_grads[cur_objective] = grad_dict

                    # NOTE: the steps here aren't accurate (due to note above about)
                    # using the same batches for objectives/losses that specify the
                    # same datasets
                    # update_tf_loss_descriptions(
                    #     grad_dict, tf_train_loss_descs_to_update
                    # )
                    # # TODO: add to tensorboard

                    # create histograms of model parameters
                    if log_cdict["track"]["tensorboard"]["param_steps"] > 0:
                        if (
                            num_training_ops
                            % log_cdict["track"]["tensorboard"]["param_steps"]
                            == 0
                        ):
                            log_model_params(tr_writer, num_training_ops, model)

                    # update Tracker
                    if log_cdict["track"]["tracker_steps"] > 0:
                        if num_training_ops % log_cdict["track"]["tracker_steps"] == 0:
                            cur_loss_tracker_dict = opt_tracker_dict[cur_objective][
                                "loss"
                            ][cur_ds_name]["train"]
                            cur_loss_update = update_loss_trackers(
                                loss_conf["track"]["train"],
                                cur_loss_tracker_dict,
                                opt_to_steps[cur_optimizer_name],
                                num_training_ops,
                                tb_writer=tr_writer,
                                ds_name=cur_ds_name,
                                objective_name=cur_objective,
                            )

                            loss_update_dict[cur_objective] = cur_loss_update

                    # TODO: this is a hacky way of seeing if training on a batch was run
                    if obj_to_grads:
                        update_model_params(
                            apply_grads_fn, obj_to_grads, model, cur_tf_optimizer
                        )

                        update_metric_objects(
                            metrics_objective_names,
                            objectives_dict,
                            obj_to_grads,
                            "train",
                        )

                        if log_cdict["track"]["tracker_steps"] > 0:
                            if (
                                num_training_ops % log_cdict["track"]["tracker_steps"]
                                == 0
                            ):
                                update_metrics_dict = update_metrics_tracking(
                                    metrics_objective_names,
                                    objectives_dict,
                                    opt_tracker_dict,
                                    obj_to_grads,
                                    opt_to_steps[cur_optimizer_name],
                                    num_training_ops,
                                    "train",
                                    tb_writer=tr_writer,
                                    ds_name=cur_ds_name,
                                    objective_name=cur_objective,
                                )

                update_dict = {"loss": loss_update_dict, "metrics": update_metrics_dict}
            continue_optimizer = False
        # one pass of training (a batch from each objective) with the
        # current optimizer

    # TODO: I think the 'joint' should likely be the optimizer name, not the
    # combination of losses name, this would also simplify the creation of these

    return_dict = {"tracker": main_tracker_dict}

    return return_dict

    # # TODO: adjust
    # train_best_joint_update = record_joint_losses(
    #     "train",
    #     "epoch",
    #     e,
    #     joint_dict_tracker,
    #     joint_loss_name,
    #     joint_loss_record_train,
    # )

    # TODO: save best params with update dict and save params
    # accordingly
    # TODO: use early_stopping:epochs and early_stopping:warmup
    # if cur_val_loss_ < best_val_loss:
    #     if e == 0:
    #         # on the first time params are saved, try to save the model
    #         model.save(save_model_path)
    #         logger.debug(f"model saved to: {save_model_path}")
    #     best_val_loss = cur_val_loss_
    #     model.save_weights(save_best_param_path)

    #     logger.debug(f"best params saved: val loss:
    #     {cur_val_loss_:.4f}")
