package compliance.authentication.resource.verify.helpers.policy_0152

# Auto-generated policy 152 (Rego v1 syntax)
# Package: compliance.authentication.resource.verify.helpers

# Metadata
metadata := {
    "policy_id": "0152",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
policy_0152_allowed if {
    input.user.active
    input.resource.public
}
policy_0152_denied if {
    input.action == "delete"
    input.user.role != "admin"
}
policy_0152_approved if {
    input.user.risk_score < 50
    input.system.health > 0.8
}
