# MMPose 1.x – HRNet-W32 für Horse-10 (22 KP, Oxford VGG Schema)
# Checkpoint: hrnet_w32_horse10_256x256_split1.pth (0.x Format, compat via _load_state_dict_pre_hook)
# Inference-only config – keine _base_-Includes, kein xtcocotools-Import.

default_scope = 'mmpose'

codec = dict(
    type='MSRAHeatmap',
    input_size=(256, 256),
    heatmap_size=(64, 64),
    sigma=2)

model = dict(
    type='TopdownPoseEstimator',
    data_preprocessor=dict(
        type='PoseDataPreprocessor',
        mean=[123.675, 116.28, 103.53],
        std=[58.395, 57.12, 57.375],
        bgr_to_rgb=True),
    backbone=dict(
        type='HRNet',
        in_channels=3,
        extra=dict(
            stage1=dict(
                num_modules=1, num_branches=1, block='BOTTLENECK',
                num_blocks=(4,), num_channels=(64,)),
            stage2=dict(
                num_modules=1, num_branches=2, block='BASIC',
                num_blocks=(4, 4), num_channels=(32, 64)),
            stage3=dict(
                num_modules=4, num_branches=3, block='BASIC',
                num_blocks=(4, 4, 4), num_channels=(32, 64, 128)),
            stage4=dict(
                num_modules=3, num_branches=4, block='BASIC',
                num_blocks=(4, 4, 4, 4), num_channels=(32, 64, 128, 256))),
        init_cfg=None),
    head=dict(
        type='HeatmapHead',
        in_channels=32,
        out_channels=22,
        # kein Deconv – entspricht SimpleHead mit num_deconv_layers=0
        deconv_out_channels=None,
        loss=dict(type='KeypointMSELoss', use_target_weight=True),
        decoder=codec),
    test_cfg=dict(
        flip_test=False,
        flip_mode='heatmap',
        shift_heatmap=True))

# Metainfo inline – vermeidet Horse10Dataset-Import und xtcocotools-Abhängigkeit.
# Oxford VGG Horse-10 Keypoints (22 KP):
_horse10_meta = dict(
    dataset_name='horse10',
    num_keypoints=22,
    keypoint_info={
        0: dict(name='Nose',             id=0,  color=[255, 255, 255], type='upper', swap=''),
        1: dict(name='Eye',              id=1,  color=[200, 220, 255], type='upper', swap=''),
        2: dict(name='Nearknee',         id=2,  color=[100, 220, 100], type='lower', swap='Offknee'),
        3: dict(name='Nearfrontfetlock', id=3,  color=[  0, 200,   0], type='lower', swap='Offfrontfetlock'),
        4: dict(name='Nearfrontfoot',    id=4,  color=[  0, 180,   0], type='lower', swap='Offfrontfoot'),
        5: dict(name='Offknee',          id=5,  color=[100, 200, 180], type='lower', swap='Nearknee'),
        6: dict(name='Offfrontfetlock',  id=6,  color=[  0, 180, 150], type='lower', swap='Nearfrontfetlock'),
        7: dict(name='Offfrontfoot',     id=7,  color=[  0, 160, 130], type='lower', swap='Nearfrontfoot'),
        8: dict(name='Shoulder',         id=8,  color=[168, 216, 168], type='upper', swap=''),
        9: dict(name='Midshoulder',      id=9,  color=[200, 230, 200], type='upper', swap=''),
       10: dict(name='Elbow',            id=10, color=[150, 220, 150], type='upper', swap=''),
       11: dict(name='Girth',            id=11, color=[240, 240, 200], type='upper', swap=''),
       12: dict(name='Wither',           id=12, color=[168, 216, 234], type='upper', swap=''),
       13: dict(name='Nearhindhock',     id=13, color=[100, 180, 255], type='lower', swap='Offhindhock'),
       14: dict(name='Nearhindfetlock',  id=14, color=[  0, 150, 255], type='lower', swap='Offhindfetlock'),
       15: dict(name='Nearhindfoot',     id=15, color=[  0, 120, 220], type='lower', swap='Offhindfoot'),
       16: dict(name='Hip',              id=16, color=[200, 180, 255], type='upper', swap=''),
       17: dict(name='Stifle',           id=17, color=[180, 150, 255], type='lower', swap=''),
       18: dict(name='Offhindhock',      id=18, color=[150, 120, 230], type='lower', swap='Nearhindhock'),
       19: dict(name='Offhindfetlock',   id=19, color=[120, 100, 210], type='lower', swap='Nearhindfetlock'),
       20: dict(name='Offhindfoot',      id=20, color=[ 90,  80, 190], type='lower', swap='Nearhindfoot'),
       21: dict(name='Ischium',          id=21, color=[230, 200, 200], type='upper', swap=''),
    },
    skeleton_info={},
    joint_weights=[1.] * 22,
    sigmas=[0.025] * 22)

test_dataloader = dict(
    dataset=dict(
        metainfo=_horse10_meta,
        pipeline=[
            dict(type='LoadImage'),
            dict(type='GetBBoxCenterScale'),
            dict(type='TopdownAffine', input_size=codec['input_size']),
            dict(type='PackPoseInputs'),
        ]))
