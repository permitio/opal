package compliance.monitoring.resource.validate.policy_0288

# Auto-generated policy 288 (Rego v1 syntax)
# Package: compliance.monitoring.resource.validate

# Metadata
metadata := {
    "policy_id": "0288",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
policy_0288_denied if {
    input.action == "delete"
    input.user.role != "admin"
}
policy_0288_allowed if {
    input.user.active
    input.resource.public
}
policy_0288_allowed if {
    data.policies.compliance.enabled
}
policy_0288_allowed if {
    input.user.role == "admin"
}
