import {aws_codecommit, CfnOutput, RemovalPolicy, Stack, StackProps, Tags} from 'aws-cdk-lib';
import {Construct} from 'constructs';
import * as iam from 'aws-cdk-lib/aws-iam';
import * as s3 from 'aws-cdk-lib/aws-s3'
import * as codebuild from 'aws-cdk-lib/aws-codebuild'
import * as codepipeline from 'aws-cdk-lib/aws-codepipeline'
import * as codepipeline_actions from 'aws-cdk-lib/aws-codepipeline-actions';
import {S3Trigger} from 'aws-cdk-lib/aws-codepipeline-actions';
import {Function, Runtime, AssetCode} from 'aws-cdk-lib/aws-lambda'
import * as ssm from 'aws-cdk-lib/aws-ssm'
import * as events from 'aws-cdk-lib/aws-events'
import * as fs from 'fs'

export class FipStack extends Stack {
  constructor(scope: Construct, id: string, props?: StackProps) {
    super(scope, id, props);

    /**
     * Resources: FIP Service Roles.
     */
    const fipServiceRole = new iam.Role(
      this,
      `${id}-${props?.env?.region}-FipServiceRole`,
      {
        assumedBy: new iam.CompositePrincipal(
          new iam.ServicePrincipal('codepipeline.amazonaws.com'),
          new iam.ServicePrincipal('codebuild.amazonaws.com'),
          new iam.ServicePrincipal('lambda.amazonaws.com'),
        ),
      },
    );
    fipServiceRole.addManagedPolicy(iam.ManagedPolicy.fromAwsManagedPolicyName('AdministratorAccess'));

    /**
     * Resources: S3 Buckets.
     */

    /**
     * [2022-02-24] KSH:
     * StackId is set at deployment time, so we cannot use this for bucket name suffix.
     * TODO: Find a way to pass the whole "AWS::StackId" to synthesized template with Fn::Join or other functions.
     */
    // const stackId: string = Stack.of(this).stackId;
    // console.log(`StackId: ${stackId}`);
    // const stackIdPart: string = this.stackId.split('/')[2];
    // console.log(`StackIdPart: ${stackIdPart}`);

    const account: string = Stack.of(this).account;
    console.log(`accound: ${account}`);
    const uid: string = this.node.addr;
    console.log(`uid: ${uid}`);
    const bucketId: string = `fip-bucket-${account}-${uid}`.substr(0, 63);
    const fipBucket = new s3.Bucket(
      this,
      // `fip-bucket-${account}-${uid}`,
      bucketId,
      {
        bucketName: bucketId,
        autoDeleteObjects: true,
        removalPolicy: RemovalPolicy.DESTROY,
        versioned: true,
      }
    );

    // const fipBucket2 = new s3.CfnBucket(
    //   this,
    //   `fip-bucket-${bucketNameSuffix}2`,
    //   {
    //     bucketName: Fn.join(
    //       '-',
    //       ['fip-bucket', "AWS::StackId"]
    //     ),
    //
    //   }
    // );

    // const fipBucket2 = new CfnResource(
    //   this,
    //   'MyBucket',
    //   {
    //     type: "AWS::S3::Bucket",
    //     properties: {
    //       BucketName: Fn.join(
    //         '-',
    //         ['fip-bucket', 'AWS::StackId']
    //       )
    //     },
    //   },
    // );
    // fipBucket2.

    /**
     * [2022-02-24] KSH: Experiment for CodeCommit.
     * TODO: Later.
     */
    // const orchestratorSourceRepo = new aws_codecommit.Repository(
    //   this,
    //   `${id}-fip-orchestrator-source-codecommit`,
    //   {
    //     repositoryName: `fip-orchestrator-source-codecommit`
    //   }
    // );
    // const orchestratorSourceOutput = new codepipeline.Artifact();
    // const orchestratorSourceAction = new codepipeline_actions.CodeCommitSourceAction(
    //   {
    //     actionName: 'Pull_Source',
    //     repository: orchestratorSourceRepo,
    //     branch: 'main',
    //     output: orchestratorSourceOutput
    //   }
    // );

    /**
     * Resources: CodePipeline - Orchestrator.
     */
    const fipOrchestratorPipeline = new codepipeline.Pipeline(
      this,
      `${id}-fip-orchestrator-pipeline`,
      {
        pipelineName: 'fip-pipeline-orchest'
      }
    );

    const fipOrchestratorSourceOutput = new codepipeline.Artifact('SourceArtifact');
    // TODO: How about CodeCommit?
    const fipOrchestratorSourceAction = new codepipeline_actions.S3SourceAction(
      {
        actionName: 'Source',
        bucket: fipBucket,
        bucketKey: 'fip-source-orchest.zip',
        output: fipOrchestratorSourceOutput,
        trigger: S3Trigger.NONE,
      }
    );

    // Add source stage to the pipeline.
    fipOrchestratorPipeline.addStage(
      {
        stageName: 'Source',
        // actions: [fipOrchestratorSourceAction, orchestratorSourceAction]
        actions: [fipOrchestratorSourceAction]
      },
    );

    /**
     * Resources: CodeBuild Projects.
     */
    // Pre build.
    const fipOrchestratorPreBuild = new codebuild.PipelineProject(
      this,
      `${id}-fip-orchestrator-pre-codebuild`,
      {
        projectName: 'fip-orchest-pre-build',
        role: fipServiceRole,
        // cache: codebuild.Cache.local(codebuild.LocalCacheMode.DOCKER_LAYER, codebuild.LocalCacheMode.CUSTOM),
        cache: codebuild.Cache.local(codebuild.LocalCacheMode.DOCKER_LAYER),
        environment: {
          buildImage: codebuild.LinuxBuildImage.AMAZON_LINUX_2,
          computeType: codebuild.ComputeType.SMALL,
          privileged: true		// We need to build the Docker image.
        },
        environmentVariables: {
          'ENV_VAR_01': {
            value: 'TODO'
          }
        },
        description: "FIP Orchestrator Preprocess CodeBuild",
        buildSpec: codebuild.BuildSpec.fromSourceFilename('buildspec_orchest_pre.yaml')
      }
    );
    const fipOrchestratorPreBuildOutput = new codepipeline.Artifact();
    const fipOrchestratorPreBuildAction = new codepipeline_actions.CodeBuildAction(
      {
        actionName: 'OrchestPre',
        project: fipOrchestratorPreBuild,
        input: fipOrchestratorSourceOutput,
        outputs: [fipOrchestratorPreBuildOutput],
      }
    );
    fipOrchestratorPipeline.addStage(
      {
        stageName: 'OrchestPre',
        actions: [fipOrchestratorPreBuildAction]
      }
    );

    // Main build.
    const fipOrchestratorMainBuild = new codebuild.PipelineProject(
      this,
      `${id}-fip-orchestrator-main-codebuild`,
      {
        projectName: 'fip-orchest-main-build',
        role: fipServiceRole,
        cache: codebuild.Cache.local(codebuild.LocalCacheMode.DOCKER_LAYER),
        environment: {
          buildImage: codebuild.LinuxBuildImage.AMAZON_LINUX_2,
          computeType: codebuild.ComputeType.SMALL,
          privileged: true		// We need to build the Docker image.
        },
        environmentVariables: {
          'ENV_VAR_01': {
            value: 'TODO'
          }
        },
        description: "FIP Orchestrator Main CodeBuild",
        buildSpec: codebuild.BuildSpec.fromSourceFilename('buildspec_orchest_main.yaml')
      }
    );
    const fipOrchestratorMainBuildOutput = new codepipeline.Artifact();
    const fipOrchestratorMainBuildAction = new codepipeline_actions.CodeBuildAction(
      {
        actionName: 'OrchestMain',
        project: fipOrchestratorMainBuild,
        input: fipOrchestratorSourceOutput,
        outputs: [fipOrchestratorMainBuildOutput],
      }
    );
    fipOrchestratorPipeline.addStage(
      {
        stageName: 'OrchestMain',
        actions: [fipOrchestratorMainBuildAction]
      }
    );

    // Post build.
    const fipOrchestratorPostBuild = new codebuild.PipelineProject(
      this,
      `${id}-fip-orchestrator-post-codebuild`,
      {
        projectName: 'fip-orchest-post-build',
        role: fipServiceRole,
        cache: codebuild.Cache.local(codebuild.LocalCacheMode.DOCKER_LAYER),
        environment: {
          buildImage: codebuild.LinuxBuildImage.AMAZON_LINUX_2,
          computeType: codebuild.ComputeType.SMALL,
          privileged: true		// We need to build the Docker image.
        },
        environmentVariables: {
          'ENV_VAR_01': {
            value: 'TODO'
          }
        },
        description: "FIP Orchestrator Post CodeBuild",
        buildSpec: codebuild.BuildSpec.fromSourceFilename('buildspec_orchest_post.yaml')
      }
    );
    const fipOrchestratorPostBuildOutput = new codepipeline.Artifact();
    const fipOrchestratorPostBuildAction = new codepipeline_actions.CodeBuildAction(
      {
        actionName: 'OrchestPost',
        project: fipOrchestratorPostBuild,
        input: fipOrchestratorSourceOutput,
        outputs: [fipOrchestratorPostBuildOutput],
      }
    );
    fipOrchestratorPipeline.addStage(
      {
        stageName: 'OrchestPost',
        actions: [fipOrchestratorPostBuildAction]
      }
    );

    /**
     * Resources: CodePipeline - Injector.
     */
    const fipInjectorPipeline = new codepipeline.Pipeline(
      this,
      `${id}-fip-injector-pipeline`,
      {
        pipelineName: 'fip-pipeline-inject'
      }
    );

    const fipInjectorSourceOutput = new codepipeline.Artifact('SourceArtifact');
    // TODO: How about CodeCommit?
    const fipInjectorSourceAction = new codepipeline_actions.S3SourceAction(
      {
        actionName: 'Source',
        bucket: fipBucket,
        bucketKey: 'fip-source-inject.zip',
        output: fipInjectorSourceOutput,
        trigger: S3Trigger.NONE,
      }
    );

    // Add source stage to the pipeline.
    fipInjectorPipeline.addStage(
      {
        stageName: 'Source',
        actions: [fipInjectorSourceAction]
      },
    );

    /**
     * Resources: CodeBuild Projects - Inject.
     */
    // Pre build.
    const fipInjectorBuild = new codebuild.PipelineProject(
        this,
        `${id}-fip-injector-codebuild`,
        {
          projectName: 'fip-inject-build',
          role: fipServiceRole,
          // cache: codebuild.Cache.local(codebuild.LocalCacheMode.DOCKER_LAYER, codebuild.LocalCacheMode.CUSTOM),
          cache: codebuild.Cache.local(codebuild.LocalCacheMode.DOCKER_LAYER),
          environment: {
            buildImage: codebuild.LinuxBuildImage.AMAZON_LINUX_2,
            computeType: codebuild.ComputeType.SMALL,
            privileged: true		// We need to build the Docker image.
          },
          environmentVariables: {
            'ENV_VAR_01': {
              value: 'TODO'
            }
          },
          description: "FIP Injector CodeBuild",
          buildSpec: codebuild.BuildSpec.fromSourceFilename('buildspec_inject.yaml')
        }
      );
    const fipInjectorBuildOutput = new codepipeline.Artifact();
    const fipInjectorBuildAction = new codepipeline_actions.CodeBuildAction(
      {
        actionName: 'Inject',
        project: fipInjectorBuild,
        input: fipInjectorSourceOutput,
        outputs: [fipInjectorBuildOutput],
      }
    );
    fipInjectorPipeline.addStage(
      {
        stageName: 'Inject',
        actions: [fipInjectorBuildAction]
      }
    );

    /**
     * Lambda Functions.
     */
    // Logger function.
    const loggerFunction = new Function(
      this,
      'fip-func-logger',
      {
        functionName: 'fip-func-logger',
        handler: 'fip-func-logger.lambda_handler',
        runtime: Runtime.PYTHON_3_8,
        memorySize: 512,
        code: new AssetCode('./resources/lambda'),
        role: fipServiceRole
      },
    );

    // Stop injector function.
    const stopInjectorFunction = new Function(
      this,
      'fip-func-stop-injector',
      {
        functionName: 'fip-func-stop_inject',
        handler: 'fip-func-stop-injector.lambda_handler',
        runtime: Runtime.PYTHON_3_8,
        memorySize: 512,
        code: new AssetCode('./resources/lambda'),
        role: fipServiceRole
      },
    );

    /**
     * Resources: SSM Parameter Stores.
     */
    // FipParameters
    const fipParametersString = fs.readFileSync('./resources/ssm/fip-parameters.json').toString();
    console.log(`FipParameters: `, fipParametersString);
    // const fipParametersJson = JSON.parse(fipParametersString);
    const fipParameters = new ssm.StringParameter(
      this,
      `${id}-fip-parameters`,
      {
        parameterName: 'fip-parameters',
        stringValue: fipParametersString,
        description: 'FIP Parameters',
      }
    );
    Tags.of(fipParameters).add('Environment', 'DEV');

    // FipParametersSource - Entry Point
    const fipParametersSource = new ssm.StringParameter(
      this,
      `${id}-fip-parameters-source`,
      {
        parameterName: 'fip-parameters-source',
        stringValue: 'fip-parameters',
        description: 'FIP Parameters Source'
      }
    );
    Tags.of(fipParametersSource).add('Environment', 'DEV');

    // FipSSM
    const fipSSMString = fs.readFileSync('./resources/ssm/fip-ssm.json').toString();
    console.log(`FipSSM: `, fipSSMString);
    const fipSSM = new ssm.StringParameter(
      this,
      `${id}-fip-ssm`,
      {
        parameterName: 'fip-ssm',
        stringValue: fipSSMString,
        description: 'FIP-SSM',
      }
    );
    Tags.of(fipSSM).add('Environment', 'DEV');

    // FipChaosMeshExampleYaml1
    const fipChaosMeshExampleYaml1String = fs.readFileSync('./resources/ssm/fip-example-chaos-mesh-pod-kill.yaml').toString();
    console.log(`FipChaosMeshExampleYaml1String: `, fipChaosMeshExampleYaml1String);
    const fipChaosMeshExampleYaml1 = new ssm.StringParameter(
      this,
      `${id}-fip-example-chaos-mesh-pod-kill`,
      {
        parameterName: 'fip-example-chaos-mesh-pod-kill',
        stringValue: fipChaosMeshExampleYaml1String,
        description: 'Example Chaos Mesh scenario template',
      }
    );
    Tags.of(fipChaosMeshExampleYaml1).add('fip', 'no');

    // FipChaosMeshExampleYaml2
    const fipChaosMeshExampleYaml2String = fs.readFileSync('./resources/ssm/fip-example-chaos-mesh-pod-failure.yaml').toString();
    console.log(`FipChaosMeshExampleYaml2String: `, fipChaosMeshExampleYaml2String);
    const fipChaosMeshExampleYaml2 = new ssm.StringParameter(
      this,
      `${id}-fip-example-chaos-mesh-pod-failure`,
      {
        parameterName: 'fip-example-chaos-mesh-pod-failure',
        stringValue: fipChaosMeshExampleYaml2String,
        description: 'Example Chaos Mesh scenario template',
      }
    );
    Tags.of(fipChaosMeshExampleYaml2).add('fip', 'no');

    // FipChaosMeshExampleYaml3
    const fipChaosMeshExampleYaml3String = fs.readFileSync('./resources/ssm/fip-example-chaos-mesh-network-delay.yaml').toString();
    console.log(`FipChaosMeshExampleYaml3String: `, fipChaosMeshExampleYaml3String);
    const fipChaosMeshExampleYaml3 = new ssm.StringParameter(
      this,
      `${id}-fip-example-chaos-mesh-network-delay`,
      {
        parameterName: 'fip-example-chaos-mesh-network-delay',
        stringValue: fipChaosMeshExampleYaml3String,
        description: 'Example Chaos Mesh scenario template',
      }
    );
    Tags.of(fipChaosMeshExampleYaml3).add('fip', 'no');

    // FipChaosMeshExampleYaml4
    const fipChaosMeshExampleYaml4String = fs.readFileSync('./resources/ssm/fip-example-chaos-mesh-network-delay-with-target.yaml').toString();
    console.log(`FipChaosMeshExampleYaml4String: `, fipChaosMeshExampleYaml4String);
    const fipChaosMeshExampleYaml4 = new ssm.StringParameter(
      this,
      `${id}-fip-example-chaos-mesh-network-delay-with-target`,
      {
        parameterName: 'fip-example-chaos-mesh-network-delay-with-target',
        stringValue: fipChaosMeshExampleYaml4String,
        description: 'Example Chaos Mesh scenario template',
      }
    );
    Tags.of(fipChaosMeshExampleYaml4).add('fip', 'no');

    // FipChaosMeshExampleYaml5
    const fipChaosMeshExampleYaml5String = fs.readFileSync('./resources/ssm/fip-example-chaos-mesh-network-delay-with-external.yaml').toString();
    console.log(`FipChaosMeshExampleYaml5String: `, fipChaosMeshExampleYaml5String);
    const fipChaosMeshExampleYaml5 = new ssm.StringParameter(
      this,
      `${id}-fip-example-chaos-mesh-network-delay-with-external`,
      {
        parameterName: 'fip-example-chaos-mesh-network-delay-with-external',
        stringValue: fipChaosMeshExampleYaml5String,
        description: 'Example Chaos Mesh scenario template',
      }
    );
    Tags.of(fipChaosMeshExampleYaml5).add('fip', 'no');

    // FipChaosMeshExampleYaml6
    const fipChaosMeshExampleYaml6String = fs.readFileSync('./resources/ssm/fip-example-chaos-mesh-network-partition.yaml').toString();
    console.log(`FipChaosMeshExampleYaml6String: `, fipChaosMeshExampleYaml6String);
    const fipChaosMeshExampleYaml6 = new ssm.StringParameter(
      this,
      `${id}-fip-example-chaos-mesh-network-partition`,
      {
        parameterName: 'fip-example-chaos-mesh-network-partition',
        stringValue: fipChaosMeshExampleYaml6String,
        description: 'Example Chaos Mesh scenario template',
      }
    );
    Tags.of(fipChaosMeshExampleYaml6).add('fip', 'no');

    // FipChaosMeshExampleYaml7
    const fipChaosMeshExampleYaml7String = fs.readFileSync('./resources/ssm/fip-example-chaos-mesh-network-loss.yaml').toString();
    console.log(`FipChaosMeshExampleYaml7String: `, fipChaosMeshExampleYaml7String);
    const fipChaosMeshExampleYaml7 = new ssm.StringParameter(
      this,
      `${id}-fip-example-chaos-mesh-network-loss`,
      {
        parameterName: 'fip-example-chaos-mesh-network-loss',
        stringValue: fipChaosMeshExampleYaml7String,
        description: 'Example Chaos Mesh scenario template',
      }
    );
    Tags.of(fipChaosMeshExampleYaml7).add('fip', 'no');

    // FipChaosMeshExampleYaml8
    const fipChaosMeshExampleYaml8String = fs.readFileSync('./resources/ssm/fip-example-chaos-mesh-network-corrupt.yaml').toString();
    console.log(`FipChaosMeshExampleYaml8String: `, fipChaosMeshExampleYaml8String);
    const fipChaosMeshExampleYaml8 = new ssm.StringParameter(
      this,
      `${id}-fip-example-chaos-mesh-network-corrupt`,
      {
        parameterName: 'fip-example-chaos-mesh-network-corrupt',
        stringValue: fipChaosMeshExampleYaml8String,
        description: 'Example Chaos Mesh scenario template',
      }
    );
    Tags.of(fipChaosMeshExampleYaml8).add('fip', 'no');

    // FipChaosMeshExampleYaml9
    const fipChaosMeshExampleYaml9String = fs.readFileSync('./resources/ssm/fip-example-chaos-mesh-network-bandwidth.yaml').toString();
    console.log(`FipChaosMeshExampleYaml9String: `, fipChaosMeshExampleYaml9String);
    const fipChaosMeshExampleYaml9 = new ssm.StringParameter(
      this,
      `${id}-fip-example-chaos-mesh-network-bandwidth`,
      {
        parameterName: 'fip-example-chaos-mesh-network-bandwidth',
        stringValue: fipChaosMeshExampleYaml9String,
        description: 'Example Chaos Mesh scenario template',
      }
    );
    Tags.of(fipChaosMeshExampleYaml9).add('fip', 'no');

    // FipIstioExampleYaml1
    const fipIstioExampleYaml1String = fs.readFileSync('./resources/ssm/fip-example-Istio-delay.yaml').toString();
    console.log(`FipIstioExampleYaml1String: `, fipIstioExampleYaml1String);
    const fipIstioExampleYaml1 = new ssm.StringParameter(
      this,
      `${id}-fip-example-Istio-delay`,
      {
        parameterName: 'fip-example-Istio-delay',
        stringValue: fipIstioExampleYaml1String,
        description: 'Example Istio scenario template',
      }
    );
    Tags.of(fipIstioExampleYaml1).add('fip', 'no');

    // FipIstioExampleYaml2
    const fipIstioExampleYaml2String = fs.readFileSync('./resources/ssm/fip-example-Istio-delay2.yaml').toString();
    console.log(`FipIstioExampleYaml2String: `, fipIstioExampleYaml2String);
    const fipIstioExampleYaml2 = new ssm.StringParameter(
      this,
      `${id}-fip-example-Istio-delay2`,
      {
        parameterName: 'fip-example-Istio-delay2',
        stringValue: fipIstioExampleYaml2String,
        description: 'Example Istio scenario template',
      }
    );
    Tags.of(fipIstioExampleYaml2).add('fip', 'no');

    // FipIstioExampleYaml3
    const fipIstioExampleYaml3String = fs.readFileSync('./resources/ssm/fip-example-Istio-abort.yaml').toString();
    console.log(`FipIstioExampleYaml3String: `, fipIstioExampleYaml3String);
    const fipIstioExampleYaml3 = new ssm.StringParameter(
      this,
      `${id}-fip-example-Istio-abort`,
      {
        parameterName: 'fip-example-Istio-abort',
        stringValue: fipIstioExampleYaml3String,
        description: 'Example Istio scenario template',
      }
    );
    Tags.of(fipIstioExampleYaml3).add('fip', 'no');

    // FipLoggerParameter
    const fipLoggerParameter = new ssm.StringParameter(
      this,
      `${id}-fip-param-logger-filename`,
      {
        parameterName: 'fip-param-logger_filename',
        stringValue: '0',
        description: 'FIP logger filename parameter',
      }
    );

    // FipBucketParameter
    const fipBucketParameter = new ssm.StringParameter(
      this,
      `${id}-fip-param-bucket-name`,
      {
        parameterName: 'fip-param-bucket_name',
        stringValue: fipBucket.bucketName,
        description: 'FIP bucket parameter',
      }
    );

    /**
     * Resources: EventBridge Rule (Optional)
     */
    const fipExampleFailsafeEventBridgeRule = new events.Rule(
      this,
      `${id}-fip-example-evtbridge-failsafe`,
      {
        ruleName: 'fip-example-evtbridge-failsafe',
        description: 'FIP example Event Bridge trigger rule',
        eventPattern: {
          source: ["aws.ec2"],
          detailType: ["EC2 Instance State-change Notification"],
          detail: {
            "instance-id": ["i-01db85d3e9daa87f2"]
          }
        }
      }
    );

    new CfnOutput(this, 'FIPStackId', { value: this.stackId });
    new CfnOutput(this, 'FIPS3Bucket', { value: fipBucket.bucketName });
    new CfnOutput(this, 'FIPOrchestratorPipeline', { value: fipOrchestratorPipeline.pipelineName });
    new CfnOutput(this, 'FIPInjectorPipeline', { value: fipInjectorPipeline.pipelineName });
    new CfnOutput(this, 'FIPLoggerFunction', { value: loggerFunction.functionName });
    new CfnOutput(this, 'FIPStopInjectorFunction', { value: stopInjectorFunction.functionName });
    new CfnOutput(this, 'FIPParameters', { value: fipParameters.parameterArn });
    new CfnOutput(this, 'FIPParametersSource', { value: fipParametersSource.parameterArn });
    new CfnOutput(this, 'FIPSSM', { value: fipSSM.parameterArn });
    new CfnOutput(this, 'FIPChaosMeshExampleYaml1', { value: fipChaosMeshExampleYaml1.parameterArn });
    new CfnOutput(this, 'FIPChaosMeshExampleYaml2', { value: fipChaosMeshExampleYaml2.parameterArn });
    new CfnOutput(this, 'FIPChaosMeshExampleYaml3', { value: fipChaosMeshExampleYaml3.parameterArn });
    new CfnOutput(this, 'FIPChaosMeshExampleYaml4', { value: fipChaosMeshExampleYaml4.parameterArn });
    new CfnOutput(this, 'FIPChaosMeshExampleYaml5', { value: fipChaosMeshExampleYaml5.parameterArn });
    new CfnOutput(this, 'FIPChaosMeshExampleYaml6', { value: fipChaosMeshExampleYaml6.parameterArn });
    new CfnOutput(this, 'FIPChaosMeshExampleYaml7', { value: fipChaosMeshExampleYaml7.parameterArn });
    new CfnOutput(this, 'FIPChaosMeshExampleYaml8', { value: fipChaosMeshExampleYaml8.parameterArn });
    new CfnOutput(this, 'FIPChaosMeshExampleYaml9', { value: fipChaosMeshExampleYaml9.parameterArn });
    new CfnOutput(this, 'FIPIstioExampleYaml1', { value: fipIstioExampleYaml1.parameterArn });
    new CfnOutput(this, 'FIPIstioExampleYaml2', { value: fipIstioExampleYaml2.parameterArn });
    new CfnOutput(this, 'FIPIstioExampleYaml3', { value: fipIstioExampleYaml3.parameterArn });
    new CfnOutput(this, 'FIPLoggerParameter', { value: fipLoggerParameter.parameterArn });
    new CfnOutput(this, 'FIPBucketParameter', { value: fipBucketParameter.parameterArn });
    new CfnOutput(this, 'FIPExampleFailsafeEventBridgeRule', { value: fipExampleFailsafeEventBridgeRule.ruleName });
  }
}
