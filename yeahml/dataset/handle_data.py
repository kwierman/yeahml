import tensorflow as tf

from yeahml.build.components.dtype import return_dtype


def augment_image(img_tensor, gt_tensor, aug_opts: dict) -> tuple:
    raise NotImplementedError


def get_parse_type(parse_dict: dict):
    tfr_obj = None
    tf_parse_type = parse_dict["tftype"].lower()
    if tf_parse_type == "fixedlenfeature":
        tfr_obj = tf.io.FixedLenFeature([], return_dtype(parse_dict["in_type"]))
    elif tf_parse_type == "fixedlensequencefeature":
        tfr_obj = tf.io.FixedLenSequenceFeature(
            [], return_dtype(parse_dict["in_type"]), allow_missing=True
        )
    else:
        raise ValueError(
            "tf_parse_type: {tf_parse_type} -- is not supported or defined"
        )
    return tfr_obj


def _parse_function(
    example_proto,
    set_type: str,
    standardize_img: bool,
    aug_opts: dict,
    parse_shape: list,
    one_hot: bool,
    output_dim: int,
    data_in_dict: dict,
    data_out_dict: dict,
    tfr_parse_dict: dict,
):

    # TODO: this logic is sloppy.. and needs to be better organized

    f_dict = tfr_parse_dict["feature"]
    featureName = f_dict["name"]

    l_dict = tfr_parse_dict["label"]
    labelName = l_dict["name"]

    feature_dict = {
        featureName: get_parse_type(f_dict),
        labelName: get_parse_type(l_dict),
    }

    # decode
    parsed_features = tf.io.parse_single_example(example_proto, features=feature_dict)

    ## Feature

    # decode string
    if f_dict["in_type"] == "string" and f_dict["dtype"] != "string":
        image = tf.io.decode_raw(
            parsed_features[featureName], return_dtype(f_dict["dtype"])
        )
        image = tf.dtypes.cast(image, dtype=tf.float32)
    else:
        image = parsed_features[featureName]

    # if a reshape is present in the config for the feature, reshape the data
    try:
        if data_in_dict["reshape_to"]:
            image = tf.reshape(image, parse_shape)
    except KeyError:
        image = tf.reshape(image, parse_shape)

    # try:
    #     if data_in_dict["cast_to"]:

    # except KeyError:
    #     image = tf.reshape(image, parse_shape)

    ## Label

    # decode string
    if l_dict["in_type"] == "string":
        label = tf.io.decode_raw(
            parsed_features[labelName], return_dtype(l_dict["dtype"])
        )
        # if a reshape is present in the config for the label, reshape the data
    else:
        label = parsed_features[labelName]

    if one_hot:
        # [-1] needed to remove the added batching
        label = tf.one_hot(label, depth=output_dim)

    # handle shape
    try:
        if data_out_dict["reshape_to"]:
            label = tf.reshape(label, data_out_dict["reshape_to"])
    except KeyError:
        label = tf.reshape(label, data_out_dict["dim"])

    # augmentation
    if aug_opts:
        if set_type == "train":
            image, label = augment_image(image, label, aug_opts)
        elif set_type == "val":
            try:
                if aug_opts["aug_val"]:
                    image, label = augment_image(image, label, aug_opts)
            except KeyError:
                pass
        else:  # test
            pass

    if standardize_img:
        image = tf.image.per_image_standardization(image)

    # return image, label, inst_id
    return image, label


def return_batched_iter(set_type: str, main_cdict: dict, hp_cdict: dict, tfr_f_path):

    try:
        aug_opts = main_cdict["augmentation"]
    except KeyError:
        aug_opts = None

    try:
        standardize_img = main_cdict["image_standardize"]
    except KeyError:
        standardize_img = False

    # TODO: revamp this. This calculation should be performed in the parse fn
    # the config file will also need to be adjusted
    if main_cdict["reshape_in_to"]:
        parse_shape = main_cdict["reshape_in_to"]
        if main_cdict["reshape_in_to"][0] != -1:
            parse_shape = main_cdict["reshape_in_to"]
        else:  # e.g. [-1, 28, 28, 1]
            parse_shape = main_cdict["reshape_in_to"][1:]
    else:
        if main_cdict["in_dim"][0]:
            parse_shape = main_cdict["in_dim"]
        else:  # e.g. [None, 28, 28, 1]
            parse_shape = main_cdict["in_dim"][1:]
    # parse_shape = list(parse_shape)

    # TODO: implement directory or files logic
    # tf.data.Dataset.list_files
    dataset = tf.data.TFRecordDataset(tfr_f_path)
    dataset = dataset.map(
        lambda x: _parse_function(
            x,
            set_type,
            standardize_img,
            aug_opts,
            parse_shape,
            main_cdict["label_one_hot"],
            main_cdict["output_dim"][-1],  # used for one_hot encoding
            main_cdict["data_in_dict"],
            main_cdict["data_out_dict"],
            main_cdict["TFR_parse"],
        )
    )  # Parse the record into tensors.
    # if set_type == "train":
    #     # TODO: try
    #     # TODO: does this belong in hp_cdict?
    #     dataset = dataset.shuffle(buffer_size=hp_cdict["shuffle_buffer"])
    # dataset = dataset.shuffle(buffer_size=1)
    # prefetch is used to ensure one batch is always ready
    # TODO: this prefetch should have some logic based on the
    # system environment, batchsize, and data size
    # TODO: a sneaky bug could appear here where the batch is applied twice
    # due to the fact that a .batch is applied to dataset objects in memory
    # TODO:
    # dataset = dataset.batch(hp_cdict["dataset"]["batch"]).prefetch(1)
    # TODO: dataset.padded_batch
    # dataset = dataset.padded_batch(
    #     batch_size, padded_shapes=(500, 1), drop_remainder=True
    # )
    # TODO: prefetch
    dataset = dataset.batch(batch_size, drop_remainder=True).prefetch(1)
    dataset = dataset.repeat(1)

    # iterator = dataset.make_initializable_iterator()

    return dataset
