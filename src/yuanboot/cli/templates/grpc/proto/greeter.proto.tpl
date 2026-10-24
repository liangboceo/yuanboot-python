syntax = "proto3";
package demo;
import "google/protobuf/wrappers.proto";
service Greeter {
  rpc Hello(google.protobuf.StringValue) returns (google.protobuf.StringValue);
}
