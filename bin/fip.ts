#!/usr/bin/env node
import 'source-map-support/register';
import * as cdk from 'aws-cdk-lib';
import {FipStack} from '../lib/fip-stack';

const app = new cdk.App();

/**
 * [2021-11-05] KSH
 * CDK_INTEG_XXX are set when producing the .expected file and CDK_DEFAULT_XXX is passed in through from the CLI in actual deployment.
 */
const env = {
  region: app.node.tryGetContext('region') || process.env.CDK_INTEG_REGION || process.env.CDK_DEFAULT_REGION,
  account: app.node.tryGetContext('account') || process.env.CDK_INTEG_ACCOUNT || process.env.CDK_DEFAULT_ACCOUNT,
};

new FipStack(
  app,
  'FipStack',
  {
    env: env
  }
);
