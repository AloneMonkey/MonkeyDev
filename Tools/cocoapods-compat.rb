# Load from a Podfile before CocoaPods reads an Xcode 27 MonkeyApp project.
# Keep these adaptations local to the current process; do not edit installed gems.
require 'cocoapods'
require 'xcodeproj'

module MonkeyDevCocoaPodsCompatibility
  module ScriptLines
    def shell_script=(value)
      super(value.is_a?(Array) ? value.join("\n") : value)
    end
  end

  module FrameworkDestination
    def configure_with_plist(objects)
      entry = objects[uuid]
      if entry.key?('dstSubfolder')
        unless entry['dstSubfolder'] == 'Frameworks'
          raise Pod::Informative, "MonkeyDev cannot safely read Copy Files destination #{entry['dstSubfolder'].inspect}. " \
            'Stop before saving the project; use a CocoaPods/xcodeproj version that supports this destination.'
        end
        entry = entry.dup
        entry.delete('dstSubfolder')
        entry['dstSubfolderSpec'] = '10'
        objects = objects.merge(uuid => entry)
      end
      super(objects)
    end
  end

  module GeneratedProjectVersion
    def create_generator(pods, aggregates, configurations, version, multiple = false)
      # Only the generated Pods project uses an older supported format.
      # Preserve the original host project's version and build configuration.
      supported = Xcodeproj::Constants::COMPATIBILITY_VERSION_BY_OBJECT_VERSION
      version = 100 if version == 110 && !supported.key?(110) && supported.key?(100)
      super(pods, aggregates, configurations, version, multiple)
    end
  end
end

Xcodeproj::Project::Object::PBXShellScriptBuildPhase.prepend(MonkeyDevCocoaPodsCompatibility::ScriptLines)
unless Xcodeproj::Project::Object::PBXCopyFilesBuildPhase.method_defined?(:dst_subfolder)
  Xcodeproj::Project::Object::PBXCopyFilesBuildPhase.prepend(MonkeyDevCocoaPodsCompatibility::FrameworkDestination)
end
Pod::Installer.prepend(MonkeyDevCocoaPodsCompatibility::GeneratedProjectVersion)
