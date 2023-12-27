import os
import torch
import cv2 as cv
from super_gradients.training import models
from drawing_util import DrawingTrackingInfo
from deep_sort_pytorch_master.deep_sort import DeepSort
from data_util import ReadData
from datetime import datetime

def tracking_by_detection(config):

    # Select device
    if config['detector_device'] == 'cuda:0':
        device_detector = torch.device('cuda:0') if torch.cuda.is_available() else torch.device('cpu')
    elif config['detector_device'] == 'cpu':
        device_detector = torch.device('cpu')
    else:
        raise ValueError('Requested device name is not correct!')
    print('Device: {}'.format(device_detector))

    # Object for reading data
    ds_object = ReadData(input_type=config['input_type'],
                         input_image_dir=config['images_folder'],
                         input_video_path=config['input_video_path'])
    ds_generator = ds_object.data_generator()

    # Load YOLO-NAS-Medium for object detecion
    detector = models.get(model_name=config['detector_arch'], pretrained_weights=config['pretrained_dataset']).to(device_detector)

    # Tracking info drawing object
    draw_obj = DrawingTrackingInfo()

    # Initialize Deep Sort with details for tracking in specified config file
    tracker = DeepSort(
                model_path=config['REID_CKPT'],
                max_dist=config['MAX_DIST'],
                min_confidence=config['MIN_CONFIDENCE'],
                nms_max_overlap=config['NMS_MAX_OVERLAP'],
                max_iou_distance=config['MAX_IOU_DISTANCE'],
                max_age=config['MAX_AGE'],
                n_init=config['N_INIT'],
                nn_budget=config['NN_BUDGET'],
                use_cuda=config['TRACKER_USE_CUDA']
            )

    img_width = None
    img_height = None
    output_video_writer = None

    # Iterate over all images
    while True:

        # Read one image
        img_i = next(ds_generator, None)
        if img_i is None:
            break
        
        if img_width is None:
            img_width, img_height = img_i.shape[1], img_i.shape[0] 
            time_str = datetime.now().strftime("%H:%M:%S")
            output_video_writer = cv.VideoWriter(os.path.join(config['output_folder'], 'output_video_{}.avi'.format(time_str)), cv.VideoWriter_fourcc('M', 'J', 'P', 'G'), 12, (img_width, img_height))
        
        # Predict bounding boxes and their label and condidence score
        output_detector = detector.predict(img_i, conf=config['detector_minimum_confidence']) 
        output_detector = list(output_detector)[0]
        bboxes = output_detector.prediction.bboxes_xyxy.tolist()
        confidences = output_detector.prediction.confidence
        labels = output_detector.prediction.labels.tolist()

        all_boxes = []
        all_labels = []
        all_confidences = []
        for (bbox_i, conf_i, label_i) in zip(bboxes, confidences, labels):
            
            if label_i not in config['objects_of_interest_labels']:
                continue

            # Two decimal confidence, for better visualization
            conf_i = round(conf_i, 2)
            
            # Upper left and bottom righ corner of bounding box
            x_ul, y_ul, x_br, y_br = [int(i) for i in bbox_i]
            
            # Center of bounding box
            x_c, y_c = (x_ul+x_br)//2, (y_ul+y_br)//2  
            
            # Width and Height of bounding box
            bbox_i_width, bbox_i_height = abs(x_ul-x_br), abs(y_ul-y_br)
            
            all_boxes.append([x_c, y_c, bbox_i_width, bbox_i_height])
            all_labels.append(int(label_i))
            all_confidences.append(conf_i)

        # Convert to tensor
        all_boxes = torch.tensor(all_boxes)
        all_confidences = torch.tensor(all_confidences)
        
        if len(all_boxes) > 0:
            # Update tracker state
            outputs = tracker.update(all_boxes, all_confidences, img_i)
        else:
            outputs = []

        # Draw tracking information on frame
        if len(outputs) > 0:
            bboxes_xyxy = outputs[:, 0:4]
            tracks_id = outputs[:, 4] 
            img_i_tracking_info = draw_obj.draw_tracking_info(image=img_i, bounding_boxes=bboxes_xyxy, tracking_ids=tracks_id)
        else:
            img_i_tracking_info = img_i 

        output_video_writer.write(cv.cvtColor(img_i_tracking_info, cv.COLOR_RGB2BGR))

    output_video_writer.release()
