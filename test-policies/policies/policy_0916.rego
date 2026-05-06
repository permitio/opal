package audit.monitoring.resource.validate.policy_0916

# Auto-generated policy 916 (Rego v1 syntax)
# Package: audit.monitoring.resource.validate

# Metadata
metadata := {
    "policy_id": "0916",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
policy_0916_allowed if {
    data.policies.audit.enabled
}
policy_0916_denied if {
    input.action == "delete"
    input.user.role != "admin"
}
policy_0916_allowed if {
    input.user.active
    input.resource.public
}
default policy_0916_allowed = false
