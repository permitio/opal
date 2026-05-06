package compliance.authorization.resource.check.policy_0693

# Auto-generated policy 693 (Rego v1 syntax)
# Package: compliance.authorization.resource.check

# Metadata
metadata := {
    "policy_id": "0693",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
policy_0693_allowed if {
    input.user.role == "admin"
}
policy_0693_denied if {
    input.action == "delete"
    input.user.role != "admin"
}
policy_0693_allowed if {
    data.policies.compliance.enabled
}
