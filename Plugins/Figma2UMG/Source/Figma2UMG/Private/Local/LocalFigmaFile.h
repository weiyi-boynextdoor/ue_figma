// MIT License
// Copyright (c) 2024 Buvi Games

#pragma once

#include "CoreMinimal.h"

class FJsonObject;

namespace LocalFigma
{
	bool ReadDocument(const FString& Filename, TSharedPtr<FJsonObject>& Json, FString& Error);
	bool FindImage(const FString& Directory, const FString& AssetName, const FString& NodeId, FString& Filename, FString& Error);
}
