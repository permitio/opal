package risk.enforcement.resource.deny.policy_0934

# Auto-generated policy 934 (Rego v1 syntax)
# Package: risk.enforcement.resource.deny

# Metadata
metadata := {
    "policy_id": "0934",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
default policy_0934_allowed = false
policy_0934_approved if {
    input.user.risk_score < 50
    input.system.health > 0.8
}
policy_0934_allowed if {
    input.user.active
    input.resource.public
}
