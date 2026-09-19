// MIT License
// Copyright (c) 2024 Buvi Games

#include "Local/LocalFigmaFile.h"

#include "Dom/JsonObject.h"
#include "HAL/FileManager.h"
#include "Misc/FileHelper.h"
#include "Misc/Paths.h"
#include "ObjectTools.h"
#include "Serialization/JsonSerializer.h"

bool LocalFigma::ReadDocument(const FString& Filename, TSharedPtr<FJsonObject>& Json, FString& Error)
{
	FString Text;
	Json.Reset();
	if (!FFileHelper::LoadFileToString(Text, *Filename))
	{
		Error = FString::Printf(TEXT("Cannot read local Figma file: %s"), *Filename);
		return false;
	}
	if (!FJsonSerializer::Deserialize(TJsonReaderFactory<>::Create(Text), Json) || !Json.IsValid())
	{
		Error = FString::Printf(TEXT("%s is not valid Figma REST JSON. Select a .figma/.json downloaded by the plugin or download_figma.py, not a native .fig archive."), *Filename);
		return false;
	}
	const TSharedPtr<FJsonObject>* Document = nullptr;
	FString Name, Type;
	if (!Json->TryGetStringField(TEXT("name"), Name) || Name.IsEmpty()
		|| !Json->TryGetObjectField(TEXT("document"), Document) || !Document || !Document->IsValid()
		|| !(*Document)->TryGetStringField(TEXT("type"), Type) || Type != TEXT("DOCUMENT"))
	{
		Error = FString::Printf(TEXT("%s must contain a file name and a DOCUMENT object."), *Filename);
		return false;
	}
	return true;
}

bool LocalFigma::FindImage(const FString& Directory, const FString& AssetName, const FString& NodeId, FString& Filename, FString& Error)
{
	// Enumerate the selected file's Images folder only; node names never form paths.
	TArray<FString> Files, ExactMatches, IdMatches;
	IFileManager::Get().FindFiles(Files, *FPaths::Combine(Directory, TEXT("*")), true, false);
	const FString SanitizedName = ObjectTools::SanitizeInvalidChars(AssetName, INVALID_OBJECTNAME_CHARACTERS);
	const FString Suffix = TEXT("--") + NodeId.Replace(TEXT(":"), TEXT("-"));
	for (const FString& Candidate : Files)
	{
		const FString Base = FPaths::GetBaseFilename(Candidate);
		if (Base.Equals(SanitizedName, ESearchCase::CaseSensitive))
		{
			ExactMatches.Add(Candidate);
		}
		else if (Base.EndsWith(Suffix, ESearchCase::CaseSensitive))
		{
			// Python and Unreal sanitize display names differently; IDs remain stable.
			IdMatches.Add(Candidate);
		}
	}
	const TArray<FString>& Matches = ExactMatches.IsEmpty() ? IdMatches : ExactMatches;
	if (Matches.Num() != 1)
	{
		Error = FString::Printf(TEXT("%s local image for node %s (%s) in %s. Supply exactly one image for this node."),
			Matches.IsEmpty() ? TEXT("Missing") : TEXT("Ambiguous"), *NodeId, *AssetName, *Directory);
		return false;
	}
	Filename = FPaths::Combine(Directory, Matches[0]);
	return true;
}
