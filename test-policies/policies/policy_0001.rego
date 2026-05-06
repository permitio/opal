package risk.authentication.resource.verify.policy_0001

# Auto-generated policy 1 (Rego v1 syntax)
# Package: risk.authentication.resource.verify

# Metadata
metadata := {
    "policy_id": "0001",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
policy_0001_denied if {
    input.action == "delete"
    input.user.role != "admin"
}
policy_0001_allowed if {
    input.user.role == "admin"
}
policy_0001_allowed if {
    data.policies.risk.enabled
}
default policy_0001_allowed = false
