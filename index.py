#
# Copyright 2016 Amazon.com, Inc. or its affiliates. All Rights Reserved.
# 
# Licensed under the Apache License, Version 2.0 (the "License"). You may not use this file except in compliance with
# the License. A copy of the License is located at
# 
#     http://aws.amazon.com/apache2.0/
# 
# or in the "license" file accompanying this file. This file is distributed on an "AS IS" BASIS, WITHOUT WARRANTIES OR
# CONDITIONS OF ANY KIND, either express or implied. See the License for the specific language governing permissions and
# limitations under the License.
# 
# Adapted for MYOB. Original available here: https://github.com/awslabs/ecr-cleanup-lambda

import os
import sys
sys.path.append("{}/deps".format(os.getcwd()))
import boto3
import argparse
import requests
from collections import defaultdict


REGION = os.environ.get('REGION', None)
DRYRUN = bool(os.environ.get('DRYRUN', 1))
IMAGES_TO_KEEP = int(os.environ.get('IMAGES_TO_KEEP', 1000))
REMOTE_ROLE = 'arn:aws:iam::492890214218:role/ecs-dev-read'
REMOTE_REGION = 'ap-southeast-2'
IMAGES_FOR_DELETION = defaultdict(list)
TAGS_FOR_DELETION = defaultdict(list)


def handler(event, context):

    session = boto3.session.Session()
    active_images = defaultdict(list)

    if REMOTE_ROLE is not None:
      remote_credentials = assume_role(REMOTE_ROLE)
      remote_session = boto3.Session(
    	aws_access_key_id = prod_credentials['AccessKeyId'],
    	aws_secret_access_key = prod_credentials['SecretAccessKey'],
    	aws_session_token = prod_credentials['SessionToken'],
      )
      active_images = list_active_images(remote_session,REMOTE_REGION)
      print("active images that are running in containers")
      for image in active_images:
        print("active remote image: " + image)

    active_images = list_active_images(session,REGION,active_images)
    print("active images that are running in containers")
    for image in active_images:
        print("active image: " + image)

    repositories = list_repositories(session,REGION)
    images_to_delete = find_images_for_deletion(session, REGION, repositories, active_images)
    delete_images(session, repositories, REGION)


def assume_role(role_arn):
    sts_client = boto3.client('sts')

    assumedRoleObject = sts_client.assume_role(
        RoleArn=role_arn,
        RoleSessionName="ecr-cleanup-session"
    )
    return assumedRoleObject['Credentials']
    

def list_active_images(sessn,regionname, running_images = None):

    if running_images is None:
        running_images = []

    print("discovering active images in "+regionname)
    ecs_client = sessn.client('ecs',region_name=regionname)

    listclusters_paginator = ecs_client.get_paginator('list_clusters')
    for response_listclusterpaginator in listclusters_paginator.paginate():
        for cluster in response_listclusterpaginator['clusterArns']:
            listtasks_paginator = ecs_client.get_paginator('list_tasks')
            for reponse_listtaskpaginator in listtasks_paginator.paginate(cluster=cluster,desiredStatus='RUNNING'):
                if reponse_listtaskpaginator['taskArns']:
                    describe_tasks_list = ecs_client.describe_tasks(
                        cluster=cluster,
                        tasks=reponse_listtaskpaginator['taskArns']
                    )

                    for tasks_list in describe_tasks_list['tasks']:
                        if tasks_list['taskDefinitionArn'] is not None:
                            response = ecs_client.describe_task_definition(
                                taskDefinition=tasks_list['taskDefinitionArn']
                            )
                            for container in response['taskDefinition']['containerDefinitions']:
                                if '.dkr.ecr.' in container['image'] and ":" in container['image']:
                                    if container['image'] not in running_images:
                                        running_images.append(container['image'])

    return running_images


def list_repositories(sessn, regionname = REGION):
    print("discovering repositories in "+regionname)
    ecr_client = sessn.client('ecr',region_name=regionname)

    repositories = []
    describerepo_paginator = ecr_client.get_paginator('describe_repositories')
    for response_listrepopaginator in describerepo_paginator.paginate():
        for repo in response_listrepopaginator['repositories']:
            repositories.append(repo)

    return repositories


def find_images_for_deletion(sessn, regionname, repositories, running_images = None):

    if running_images is None:
        running_images = []

    ecr_client = sessn.client('ecr',region_name=regionname)

    for repository in repositories:
        rname = repository['repositoryName']
        print("discovering images in repository :"+repository['repositoryUri'])
        images = []
        describeimage_paginator = ecr_client.get_paginator('describe_images')
        for response_describeimagepaginator in describeimage_paginator.paginate(
                registryId=repository['registryId'],
                repositoryName=repository['repositoryName']):
            for image in response_describeimagepaginator['imageDetails']:
                images.append(image)

        images.sort(key=lambda k: k['imagePushedAt'],reverse=True)

        #Get ImageDigest from ImageURL for running images. Do this for every repository
        running_sha = []
        for image in images:
            if 'imageTags' in image:
                for tag in image['imageTags']:
                    imageurl = repository['repositoryUri'] + ":" + tag
                    for running in running_images:
                        if imageurl == running:
                            if imageurl not in running_sha:
                                running_sha.append(image['imageDigest'])
        for image in images:
            if images.index(image) >= IMAGES_TO_KEEP:
                if 'imageTags' in image:
                    for tag in image['imageTags']:
                        if "latest" not in tag:
                            if running_sha:
                                if image['imageDigest'] not in running_sha:
                                    appendtolist(IMAGES_FOR_DELETION[rname], image['imageDigest'])
                                    appendtotaglist(TAGS_FOR_DELETION[rname],imageurl)

                            else:
                                appendtolist(IMAGES_FOR_DELETION[rname], image['imageDigest'])
                                appendtotaglist(TAGS_FOR_DELETION[rname],imageurl)


                else:
                    appendtolist(IMAGES_FOR_DELETION[rname], image['imageDigest'])


def delete_images(sessn, repositories, regionname):
    print("\ndelete images:")
    ecr_client = sessn.client('ecr',region_name=regionname)
    for repository in repositories:
        repoid = repository['registryId']
        reponame = repository['repositoryName']

        if not DRYRUN:
            print(reponame + " images for deletion:")
            print(IMAGES_FOR_DELETION[reponame])
    #        delete_response = ecr_client.batch_delete_image(
    #            registryId=repoid,
    #            repositoryName=repository['repositoryName'],
    #            imageIds=IMAGES_FOR_DELETION[repository]
    #         )
    #        print (delete_response)
        else:
            print(reponame + " images for deletion:")
            print(IMAGES_FOR_DELETION[reponame])

    print("\ndelete tags:")
    for repository in TAGS_FOR_DELETION.keys():
        for tag in TAGS_FOR_DELETION[repository]:
            print(repository + ": delete tag: " + tag)


def appendtolist(list,id):
    if not {'imageDigest': id} in list:
        list.append({'imageDigest': id})

def appendtotaglist(list,id):
    if not id in list:
        list.append(id)


# Below is the main harness
if __name__ == '__main__':
    request = {"None": "None"}
    parser = argparse.ArgumentParser(description='Deletes stale ECR images')
    parser.add_argument('-dryrun', help='Prints the repository to be deleted without deleting them', default='true', action='store', dest='dryrun')
    parser.add_argument('-imagestokeep', help='Number of image tags to keep', default=100, action='store', dest='imagestokeep')
    parser.add_argument('-region', help='ECR/ECS region', default=None, action='store', dest='region')

    args = parser.parse_args()
    REGION = args.region
    DRYRUN = args.dryrun.lower() != 'false'
    IMAGES_TO_KEEP = int(args.imagestokeep)
    handler(request, None)
