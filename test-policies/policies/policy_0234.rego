package compliance.authentication.resource.deny.policy_0234

# Auto-generated policy 234 (Rego v1 syntax)
# Package: compliance.authentication.resource.deny

# Metadata
metadata := {
    "policy_id": "0234",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
default policy_0234_allowed = false
policy_0234_denied if {
    input.action == "delete"
    input.user.role != "admin"
}
policy_0234_allowed if {
    data.policies.compliance.enabled
}
policy_0234_allowed if {
    input.user.role == "admin"
}
