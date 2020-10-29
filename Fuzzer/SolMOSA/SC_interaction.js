// This script connects to the Ethereum simulator that is listening at the specified port and deploys the contract and calls it's methods following the --methods argument.
const Web3 = require('web3')
const BigNumber = require('bignumber.js')
const fs = require('fs');
const Debug = require('web3-eth-debug').Debug;
const args = require('minimist')(process.argv.slice(2));
const assert = require('assert');
const options = {
    transactionConfirmationBlocks: 1,
}
var data = fs.readFileSync('tests.txt', 'utf8');
const methods = eval(data);
const port = args.ETH_port;
const web3 = new Web3(new Web3.providers.HttpProvider(port), null, options);
const debug = new Debug(new Web3.providers.HttpProvider(port), null, options);

const contract_Abi = eval(args.abi);
const bytecode = eval(args.bytecode);

const contract = new web3.eth.Contract(contract_Abi);
contract.transactionConfirmationBlocks = 1;

var toBigNumber = function(val){
  if( Number.isInteger(val)){
    return BigNumber(val).toFixed();
  }
  else if(Array.isArray(val)){
    return val.map(toBigNumber);
  }
  else{
    return val;
  }
}

async function runTest(){
  var method;
  var input_args;
  var from;
  var value;
  var deployed;
  var constHash;
  var tx;
  var txTrace;
  var constTrace;
  var constPos;
  var gas;
  var ans = [];
  var returnvals = [];
  var last_TxTrace = 0;
  var deploySuccess = false;

  for (var i = 0; i < methods.length; i++){
    try{
      last_block = await web3.eth.getBlock("latest");
    }
    catch (err){
      console.log(`tried and failed to get last block: returned error: ${err}`);
    }
    method = methods[i];
    from = method.fromAcc;
    method_name = method.name;
    if(method_name != 'passTime'){
      input_args = method.inputVars.map(toBigNumber);
    }
    else{
      // evm_increaseTime cannot handle BigNumbers.
      input_args = method.inputVars;
    }
    value = toBigNumber(method.value);

    if(method.name == 'constructor'){
      console.log('\n');
    }
    console.log(`calling ${method_name}(${input_args}) from ${from} with value ${value}`)

    if(method_name == 'constructor'){
      if(deploySuccess){
        constTrace = await debug.getTransactionTrace(constHash, {});
        ans.splice(constpos, 0, constTrace.structLogs);
        returnvals.splice(constpos, 0, "None");
      }
      else if (i > 0){
        ans.splice(constpos, 0, "ConstructorFail");
        returnvals.splice(constpos, 0, "ConstructorFail");
      }
      try{
        gas = await contract.deploy({data: bytecode, arguments: input_args}).estimateGas({
          from: from,
          value: value,
        });
        deployed = await contract.deploy({data: bytecode, arguments: input_args}).send({
          from: from,
          value: value,
          gas: gas+1
        }).on('transactionHash', (transactionHash) => {constHash = transactionHash;});
        constpos = i;
        deploySuccess = true;
      }
      catch(err){
        console.log(`Tried and failed to deploy the contract with arguments: ${input_args} and value ${value}. Error: ${err}`);
        constpos = i;
        deploySuccess = false;
      }
    }
    else if (!deploySuccess){
      console.log(`Actually not gonna call, because constructor failed.`)
      ans.push("ConstructorFail");
      returnvals.push("ConstructorFail");
      continue;
    }
    else{
      if (method_name.substring(0,8) == 'passTime') {
        web3.currentProvider.send({method: "evm_increaseTime", params: input_args},function(err, result){});
        var tempBlock = await web3.eth.getBlock("latest");
        console.log(tempBlock);
        ans.push(method_name);
        returnvals.push(method_name);
        continue;
      }
      else if (method_name.substring(0,10) == 'passBlocks') {
        web3.currentProvider.send({jsonrpc: "2.0", method: "evm_mine", params: [], id: 0}, function(err, result){});
        ans.push(method_name);
        returnvals.push(method_name);
        continue;
      }
      else{
        // See if the transaction executes without returning an error
        try {
          if (method_name == "_fallback"){
            tx = await eval(`web3.eth.sendTransaction({from: from, to: deployed.options.address, value: value})`);
          }
          else{
            tx = await eval(`deployed.methods.${method_name}.apply(this, input_args).send({from: from, value: value})`);
          }
        }
        catch(err){
          if(err.toString().search("out of gas")==66){
            // The standard amount of gas was not enough.
            gas = last_block.gasLimit;
            console.log(`Function returned out of gas error, we try again with the gasLimit: ${gas}`)
            // See if the transaction executes without returning an error
            try {
              if (method_name == "_fallback"){
                tx = await eval(`web3.eth.sendTransaction({from: from, to: deployed.options.address, value: value, gas: gas})`);
              }
              else{
                tx = await eval(`deployed.methods.${method_name}.apply(this, input_args).send({from: from, value: value, gas: gas})`);
              }
            }
            catch(error){
              if(error.toString().search("revert")==-1&&error.toString().search('Invalid JSON RPC response: ""')==-1&&error.toString().search('invalid opcode')==-1){
                // For some reason ganache randomly throws invalid opcode sometimes.
                throw `encountered an error which is not revert or invalid JSON RPC response: ${error}`
              }
              else{
                console.log("Failed after trying with more gas!")
                new_last_block = await web3.eth.getBlock("latest");
                max_iterations = 10;
                iteration=0;
                while(new_last_block.number==last_block.number&&iteration<max_iterations){
                  console.log(`Waiting for block to be processed, trying ${max_iterations-iteration-1} more times.`)
                  new_last_block = await web3.eth.getBlock("latest");
                  iteration+=1;
                }
                last_block = new_last_block;
                tx = new_last_block.transactions[new_last_block.transactions.length-1];
              }
            }
          }
          else if(err.toString().search("sender doesn't have enough funds to send tx")!=-1){
            console.log(`Balance of account ${from} is smaller than the value required for the methodcall: < ${value}.`);
            ans.push("Out of Ether");
            returnvals.push("Out of Ether");
            continue;
          }
          // Revert errors are good and should still be processed!
          else if(err.toString().search("Error: invalid address")!=-1){
            console.log(`Tried to interact with an invalid address which returned error: ${err}`);
            ans.push("Invalid Address");
            returnvals.push("Invalid Address");
            continue;
          }
          else if(err.toString().search("revert")==-1&&err.toString().search('Invalid JSON RPC response: ""')==-1&&err.toString().search('invalid opcode')==-1){
            // For some reason ganache randomly throws invalid opcode sometimes.
            throw `encountered an error which is not revert or invalid JSON RPC response: ${err}`
          }
          else{
            new_last_block = await web3.eth.getBlock("latest");
            max_iterations = 10;
            iteration=0;
            while(new_last_block.number==last_block.number&&iteration<max_iterations){
              console.log(`Waiting for block to be processed, trying ${max_iterations-iteration-1} more times.`)
              new_last_block = await web3.eth.getBlock("latest");
              iteration+=1;
            }
            last_block = new_last_block;
            tx = new_last_block.transactions[new_last_block.transactions.length-1];
          }
        }
        if(typeof(tx)=='string'){
          txTrace = await debug.getTransactionTrace(tx, {});
        }
        else{
          txTrace = await debug.getTransactionTrace(tx.transactionHash, {});
        }

        assert(last_TxTrace!=txTrace);
        last_TxTrace=txTrace;
        ans.push(txTrace.structLogs);
        returnvals.push(tx.status);
      }
    }
  }
  constTrace = await debug.getTransactionTrace(constHash, {});
  ans.splice(constpos, 0, constTrace.structLogs);
  returnvals.splice(constpos, 0, tx.status);
  return [ans, returnvals];
}

console.log("Starting a new round of tests.");
runTest().then(function(arr){
  fs.writeFileSync("debugs.txt", '['
      + arr[0].map(JSON.stringify).join(',')
    + ']');

    fs.writeFileSync("returnvals.txt", '['
        + arr[1].map(JSON.stringify).join(',')
      + ']');
  console.log("Finished")
  return arr;
});
