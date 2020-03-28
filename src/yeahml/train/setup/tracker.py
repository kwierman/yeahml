class Tracker:
    def __init__(self, to_track, step_description):
        if not to_track:
            self.to_track = None
        elif isinstance(to_track, list):
            lower = []
            for obj in to_track:
                if not isinstance(obj, str):
                    raise TypeError(f"object {obj} of {to_track} is not type string")
                else:
                    lower.append(obj.lower())
            self.to_track = lower
        elif isinstance(to_track, str):
            self.to_track = [to_track.lower()]
        else:
            raise TypeError(f"{to_track} must be a list of strings or string")

        self.values = None
        self.steps = None

        if not step_description:
            raise ValueError(f"must specify a step_description")
        elif not isinstance(step_description, str):
            raise TypeError(
                f"step_description ({step_description}) must be type string not {type(step_description)}"
            )
        self.step_description = step_description

        for obj in self.to_track:
            if obj == "max":
                self.max = None
                self.step_at_max = None
            elif obj == "min":
                self.min = None
                self.step_at_min = None
            else:
                raise ValueError(f"{obj} is not an accepted description to track")

    def update(self, step, value):
        if self.steps and self.values:
            self.steps.append(step)
            self.values.append(value)
        else:
            self.steps = [step]
            self.values = [value]
        try:
            cur_max = self.max
            if cur_max:
                if value > cur_max:
                    self.max = value
                    self.step_at_max = step
            else:
                self.max = value
                self.step_at_max = step
        except AttributeError:
            pass

        try:
            cur_min = self.min
            if cur_min:
                if value < cur_min:
                    self.min = value
                    self.step_at_min = step
        except AttributeError:
            pass

    def __str__(self):
        return str(self.__class__) + ": " + str(self.__dict__)

    def __call__(self):
        return self.__dict__


## create


def create_joint_dict_tracker(optimizer_to_loss_name_map):
    joint_dict_tracker = {}
    for _, temp_dict in optimizer_to_loss_name_map.items():
        try:
            jd = temp_dict["losses_to_optimize"]["joint_record"]
            joint_name = temp_dict["losses_to_optimize"]["joint_name"]
        except KeyError:
            pass

        if jd:
            joint_dict_tracker[joint_name] = {}
            for ds_name, do in jd.items():
                for description, met_tensor in do.items():
                    joint_dict_tracker[joint_name][ds_name] = {
                        f"{description}": {
                            "epoch": {"best": None, "steps": None, "values": None}
                        }
                    }
    return joint_dict_tracker


def create_loss_dict_tracker(optimizer_to_loss_name_map):
    loss_dict_tracker = {}
    for _, temp_dict in optimizer_to_loss_name_map.items():
        for name in temp_dict["losses_to_optimize"]["names"]:
            loss_dict_tracker[name] = {
                "train": {
                    "mean": {"epoch": {"best": None, "steps": None, "values": None}}
                    # "batch": {"best": None, "steps": None, "values": None}
                },
                "val": {
                    "mean": {"epoch": {"best": None, "steps": None, "values": None}}
                    # "batch": {"best": None, "steps": None, "values": None}
                },
            }
            # TODO: if there is another increment to log, do so here
    return loss_dict_tracker


def create_perf_dict_tracker(in_hash_to_metrics_config):
    # NOTE: this is out of order from losses:
    # losses = name : ds(train/val): description : .....
    # metrics = ds(train/val) : name : ....
    # I'm not sure which is better yet, but this should be standardized
    perf_dict_tracker = {}
    for _, temp_dict in in_hash_to_metrics_config.items():
        try:
            metric_names = temp_dict["metric_order"]
            md = temp_dict["objects"]
        except KeyError:
            pass

        if md:
            for ds_name, met_list in md.items():
                perf_dict_tracker[ds_name] = {}
                for i, met in enumerate(met_list):
                    perf_dict_tracker[ds_name][metric_names[i]] = {
                        "epoch": {"best": None, "steps": None, "values": None}
                    }
    return perf_dict_tracker


## record


def record_losses(
    ds_name, step_name, step_value, loss_dict_tracker, l2o_names, l2o_loss_record
):
    # TODO: I think we should change this logic such that we only keep track of
    # the tensor/metric name and use that as a lookup followed by a dict of
    # additional information?
    best_update = {}

    for name, mets in l2o_loss_record.items():
        # name is the name of {description?} of the metric (mean, etc.)
        if not isinstance(mets, list):
            mets = [mets]
        for i, metric_object in enumerate(mets):

            if not loss_dict_tracker[l2o_names[i]][ds_name][name][step_name]["steps"]:
                loss_dict_tracker[l2o_names[i]][ds_name][name][step_name]["steps"] = [
                    step_value
                ]
            else:
                loss_dict_tracker[l2o_names[i]][ds_name][name][step_name][
                    "steps"
                ].append(step_value)

            cur_val = metric_object.result().numpy()
            if not loss_dict_tracker[l2o_names[i]][ds_name][name][step_name]["values"]:
                loss_dict_tracker[l2o_names[i]][ds_name][name][step_name]["values"] = [
                    cur_val
                ]
            else:
                loss_dict_tracker[l2o_names[i]][ds_name][name][step_name][
                    "values"
                ].append(cur_val)

            prev_best = loss_dict_tracker[l2o_names[i]][ds_name][name][step_name][
                "best"
            ]
            if not prev_best:
                loss_dict_tracker[l2o_names[i]][ds_name][name][step_name][
                    "best"
                ] = cur_val
                update = True
            else:
                # NOTE: currently assuming min
                if cur_val < prev_best:
                    loss_dict_tracker[l2o_names[i]][ds_name][name][step_name][
                        "best"
                    ] = cur_val
                    update = True
                else:
                    update = False
            best_update[l2o_names[i]] = {name: update}
            # TODO: logic with the current best

    return best_update


def record_metrics(
    ds_name, step_name, step_value, perf_dict_tracker, metric_names, mets
):
    # {
    #     "train": {
    #         "meansquarederror": {
    #             "epoch": {"best": None, "steps": None, "values": None}
    #         },
    #         "meanabsoluteerror": {
    #             "epoch": {"best": None, "steps": None, "values": None}
    #         },
    #     },
    #     "val": {
    #         "meansquarederror": {
    #             "epoch": {"best": None, "steps": None, "values": None}
    #         },
    #         "meanabsoluteerror": {
    #             "epoch": {"best": None, "steps": None, "values": None}
    #         },
    #     },
    # }

    best_update = {}
    if not isinstance(mets, list):
        mets = [mets]
    for i, metric_object in enumerate(mets):
        if not perf_dict_tracker[ds_name][metric_names[i]][step_name]["steps"]:
            perf_dict_tracker[ds_name][metric_names[i]][step_name]["steps"] = [
                step_value
            ]
        else:
            perf_dict_tracker[ds_name][metric_names[i]][step_name]["steps"].append(
                step_value
            )

        cur_value = metric_object.result().numpy()
        if not perf_dict_tracker[ds_name][metric_names[i]][step_name]["values"]:
            perf_dict_tracker[ds_name][metric_names[i]][step_name]["values"] = [
                cur_value
            ]
        else:
            perf_dict_tracker[ds_name][metric_names[i]][step_name]["values"].append(
                cur_value
            )

        prev_best = perf_dict_tracker[ds_name][metric_names[i]][step_name]["best"]
        if not prev_best:
            perf_dict_tracker[ds_name][metric_names[i]][step_name]["best"] = cur_value
            update = True
        else:
            if cur_value < prev_best:
                perf_dict_tracker[ds_name][metric_names[i]][step_name][
                    "best"
                ] = cur_value
                update = True
            else:
                update = False
        # uggghhhh.. hardcoded "result"
        best_update[metric_names[i]] = {"result": update}

    return best_update


def record_joint_losses(
    ds_name,
    step_name,
    step_value,
    joint_dict_tracker,
    joint_loss_name,
    joint_loss_record,
):

    # {
    #     "main_obj__second_obj__joint_train": {
    #         "train": {"mean": {"epoch": {"best": None, "steps": None, "values": None}}},
    #         "val": {"mean": {"epoch": {"best": None, "steps": None, "values": None}}},
    #     }
    # }

    best_update = {}
    for name, mets in joint_loss_record.items():
        if not isinstance(mets, list):
            mets = [mets]
        for i, metric_object in enumerate(mets):

            if not joint_dict_tracker[joint_loss_name][ds_name][name][step_name][
                "steps"
            ]:
                joint_dict_tracker[joint_loss_name][ds_name][name][step_name][
                    "steps"
                ] = [step_value]
            else:
                joint_dict_tracker[joint_loss_name][ds_name][name][step_name][
                    "steps"
                ].append(step_value)

            cur_val = metric_object.result().numpy()
            if not joint_dict_tracker[joint_loss_name][ds_name][name][step_name][
                "values"
            ]:
                joint_dict_tracker[joint_loss_name][ds_name][name][step_name][
                    "values"
                ] = [cur_val]
            else:
                joint_dict_tracker[joint_loss_name][ds_name][name][step_name][
                    "values"
                ].append(cur_val)

            prev_best = joint_dict_tracker[joint_loss_name][ds_name][name][step_name][
                "best"
            ]
            if not prev_best:
                joint_dict_tracker[joint_loss_name][ds_name][name][step_name][
                    "best"
                ] = cur_val
                update = True
                best_update[joint_loss_name] = {name: True}
            else:
                # NOTE: currently assuming min
                if cur_val < prev_best:
                    joint_dict_tracker[joint_loss_name][ds_name][name][step_name][
                        "best"
                    ] = cur_val
                    update = True
                else:
                    update = False
            best_update[joint_loss_name] = {name: update}
    return best_update
